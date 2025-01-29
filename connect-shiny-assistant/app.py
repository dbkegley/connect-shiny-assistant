from __future__ import annotations

import json
import os
import re
from pathlib import Path
import tarfile
import subprocess
import time
from typing import Literal, TypedDict, cast

from anthropic.types import MessageParam

from chatlas.types import Content, ContentText
from app_utils import load_dotenv
from htmltools import Tag

from chatlas import ChatAnthropic
from posit.connect import Client
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shiny.ui._card import CardItem


CONTENT_GUID = "03cbca64-2b48-417f-8db3-dfe9a7a9388e"
CONTENT_URL = "http://localhost:8989/"

# TODO: This won't work if multiple viewers using the same shiny process
SHINY_APP_DIR=(Path(__file__).parent).joinpath("shiny-app-bundle")
SHINY_APP_BUNDLE=(Path(__file__).parent).joinpath("shiny-app-bundle.tar.gz")

# Environment variables

load_dotenv()
api_key = os.environ.get("ANTHROPIC_API_KEY")
if api_key is None:
    raise ValueError("Please set the ANTHROPIC_API_KEY environment variable.")

connect_api_key = os.environ.get("CONNECT_API_KEY")
if connect_api_key is None:
    raise ValueError("Please set the CONNECT_API_KEY environment variable.")

app_dir = Path(__file__).parent


def delete_app_code():
    print("deleting app code")
    if os.path.exists(SHINY_APP_DIR):
        import shutil
        shutil.rmtree(SHINY_APP_DIR)
    if os.path.exists(SHINY_APP_BUNDLE):
        os.remove(SHINY_APP_BUNDLE)

# Read the contents of a file, where the base path defaults to current dir of this file.
def read_file(filename: Path | str, base_dir: Path = app_dir) -> str:
    with open(base_dir / filename, "r") as f:
        res = f.read()
        return res


def read_app_code() -> list[FileContent]:
    shiny_app_code = []
    for f in os.listdir(SHINY_APP_DIR):
        if os.path.isfile(os.path.join(SHINY_APP_DIR, f)):
            file_content = FileContent(
                name=f,
                content=read_file(f, base_dir=SHINY_APP_DIR),
                type="text")
            shiny_app_code.append(file_content)
    return shiny_app_code


def write_shinyapp_changes(files: list[FileContent] | None):
    if files is not None:
        for file in files:
            with open(SHINY_APP_DIR / file["name"], "w") as f:
                f.write(file["content"])


async def search_content() -> str:
    """Search for existing content on a Connect server that the current user is allowed to access"""
    client = Client()
    content = client.content.find()
    return json.dumps(content)


async def open_existing_content(guid: str) -> list[FileContent]:
    """Download content from a Connect server and open it locally for live editing"""
    print("opening existing content")
    client = Client()
    content = client.content.get(guid)
    bundle = content.bundles.get(content.bundle_id)
    bundle.download(str(SHINY_APP_BUNDLE))
    tar = tarfile.open(SHINY_APP_BUNDLE)
    tar.extractall(path=SHINY_APP_DIR)
    return read_app_code()


# def initialize_new_content(files: list[FileContent]):
#     """Create a new shiny app project as a starting point"""
#     delete_app_code()
#     os.mkdir(SHINY_APP_DIR)
#     write_shinyapp_changes(files)


process: subprocess.Popen | None = None
def start_content():
    # NOTE: subprocess.run is blocking so we have to use Popen to avoid blocking gunicorn
    global process
    if process is None:
        process = subprocess.Popen(["shiny", "run", "-r", "--port", "8989"], cwd=SHINY_APP_DIR)
        # TODO: actual synchronization
        time.sleep(5)


def stop_content():
    global process
    if process is not None:
        process.kill()
        process = None


app_prompt_template = read_file("app_prompt.md")

app_prompt_language_specific = {
    "python": read_file("app_prompt_python.md"),
}


greeting = """
Hello, I'm Shiny Assistant! I'm here to help you with [Shiny](https://shiny.posit.co),
a web framework for data driven apps. You can ask me questions about how to use Shiny,
to explain how certain things work in Shiny, or even ask me to build a Shiny app for you.

Here are some examples:

- "How do I add a plot to an application?"
- "Create an app that shows a normal distribution."
- "Show me how make it so a table will update only after a button is clicked."
- Ask me, "Open the editor", then copy and paste your existing Shiny code into the editor, and then ask me to make changes to it.

Let's get started! 🚀
"""


class FileContent(TypedDict):
    name: str
    content: str
    type: Literal["text", "binary"]


switch_tag = ui.input_switch("language_switch", "Python", True,)
switch_tag.add_style("width: unset; display: inline-block; padding: 0 20px;")
switch_tag.children[0].add_style("display: inline-block;")  # pyright: ignore
switch_tag.children[0].children[0].attrs.update({'disabled': True}) # pyright: ignore
switch_tag.insert(0, ui.tags.span("R ", style="padding-right: 0.3em;"))

verbosity_tag = ui.input_select(
    "verbosity", None, ["Code only", "Concise", "Verbose"], selected="Concise"
)
verbosity_tag.add_style("width: unset; display: inline-block; padding: 0 20px;")

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.div(class_="sidebar-resizer"),
        ui.div(
            switch_tag,
            verbosity_tag,
        ),
        ui.chat_ui("ui_chat", height="100%"),
        open="open",
        width="400px",
        style="height: 100%;",
        gap="3px",
        padding="3px",
    ),
    ui.head_content(
        ui.tags.title("Shiny Assistant"),
        ui.tags.style(read_file("style.css")),
        ui.tags.script(read_file("scripts.js")),
    ),
    ui.output_ui("shiny_iframe"),
    fillable=True,
)


for child in app_ui.children:
    if isinstance(child, Tag) and child.has_class("bslib-page-sidebar"):
        for child in child.children:
            if isinstance(child, CardItem) and cast(Tag, child._item).has_class(
                "bslib-sidebar-layout"
            ):
                cast(Tag, child._item).add_class("chat-full-width")
                break
        break


def server(input: Inputs, output: Outputs, session: Session):
    delete_app_code()
    shiny_panel_visible = reactive.value(False)
    shiny_panel_visible_smooth_transition = reactive.value(True)
    shiny_app_files: reactive.Value[list[FileContent] | None] = reactive.Value(
        None
    )

    @reactive.calc
    def app_prompt() -> str:
        verbosity_instructions = {
            "Code only": "If you are providing a Shiny app, please provide only the code."
            " Do not add any other text, explanations, or instructions unless"
            " absolutely necessary. Do not tell the user how to install Shiny or run"
            " the app, because they already know that.",
            "Concise": "Be concise when explaining the code."
            " Do not tell the user how to install Shiny or run the app, because they"
            " already know that.",
            "Verbose": "",  # The default behavior of Claude is to be verbose
        }

        prompt = app_prompt_template.format(
            language=language(),
            language_specific_prompt=app_prompt_language_specific[language()],
            verbosity=verbosity_instructions[input.verbosity()],
        )
        return prompt

    chat = ui.Chat(
        id="ui_chat",
        messages=[{"role": "assistant", "content": greeting}],
    )
    chat.ui()

    @chat.on_user_submit
    async def _():
        model = ChatAnthropic(
            api_key=api_key,
            model="claude-3-5-sonnet-20241022",
            system_prompt=app_prompt(),
            max_tokens=3000,
        )
        model.register_tool(search_content)
        model.register_tool(open_existing_content)
        messages = chat.messages(format="anthropic",
                                 token_limits=(16000, 3000),
                                 transform_assistant=True)
        # messages = remove_consecutive_messages(messages)

        # TODO: put this in the prompt?
        app_code = shiny_app_files()
        if app_code is None and os.path.exists(SHINY_APP_DIR):
            app_code = read_app_code()

        # TODO: Should this be a separate system message instead of modifying the user message?
        if app_code is not None:
            messages[-1][
                "content"
            ] = f"""
The following is the current app code in JSON format. The text that comes after this app
code might ask you to modify the code. If it does, please modify the code. If the text
does not ask you to modify the code, then ignore the code.

```
{app_code}
```

{ messages[-1]["content"] }
"""

        request = transform_messages_to_chatlas_content_format(messages)
        response = await model.stream_async(request) # echo="all"
        await chat.append_message_stream(response)


    @render.ui
    def shiny_iframe():
        return ui.tags.iframe(
            id="shiny-panel",
            src=CONTENT_URL,
            style="flex: 1 1 auto;",
            allow="clipboard-write",
        )

    #
    # ==================================================================================
    # Code for finding content in the <SHINYAPP> tags and sending to the client
    # ==================================================================================

    # async def sync_latest_messages_locked():
    #     async with reactive.lock():
    #         await sync_latest_messages()
    #
    # last_message_sent = 0
    # async def sync_latest_messages():
    #     nonlocal last_message_sent
    #
    #     with reactive.isolate():
    #         messages = chat.messages(
    #             format="anthropic",
    #             token_limits=None,
    #             transform_user="all",
    #             transform_assistant=False,
    #         )
    #
    #     new_messages = messages[last_message_sent:]
    #     last_message_sent = len(messages)
    #     if len(new_messages) > 0:
    #         print(f"Synchronizing {len(new_messages)} messages")
    #         await session.send_custom_message(
    #             "sync-chat-messages", {"messages": new_messages}
    #         )

    @chat.transform_assistant_response
    async def transform_response(content: str, chunk: str, done: bool) -> str:
        # if done:
        #     asyncio.create_task(sync_latest_messages_locked())

        # TODO: This is inefficient because it does this processing for every chunk,
        # which means it will process the same content multiple times. It would be
        # better to do this incrementally as the content streams in.

        # Only do this when streaming. (We don't to run it when restoring messages,
        # which does not use streaming.)
        if chunk != "":
            async with reactive.lock():
                with reactive.isolate():
                    # If we see the <SHINYAPP> tag, make sure the shiny panel is
                    # visible.
                    if '<SHINYAPP AUTORUN="1">' in content:
                        # Everytime we see a </SHINYAPP> tag, set the file content.
                        if "</SHINYAPP>" in content:
                            files = transform_shinyapp_tag_contents_to_filecontents(content)
                            shiny_app_files.set(files)
                        await reactive.flush()

        content = re.sub(
            '<SHINYAPP AUTORUN="[01]">', "<div class='assistant-shinyapp'>\n", content
        )
        # TODO: Don't write changes to disk util confirmation is clicked
        # content = content.replace(
        #     "</SHINYAPP>",
        #     "\n<div class='run-code-button-container'>"
        #     "<button class='run-code-button btn btn-outline-primary'>Apply changes →</button>"
        #     "</div>\n</div>",
        # )
        content = re.sub(
            '\n<FILE NAME="(.*?)">',
            r"\n<div class='assistant-shinyapp-file'>\n<div class='filename'>\1</div>\n\n```",
            content,
        )
        content = content.replace("\n</FILE>", "\n```\n</div>")

        return content


    @reactive.effect
    @reactive.event(shiny_app_files)
    async def _send_shinyapp_code():
        if shiny_app_files() is None:
            return

        print("syncing files on disk")
        write_shinyapp_changes(shiny_app_files())
        start_content()
        shiny_panel_visible.set(True)
        # await session.send_custom_message(
        #     "set-shiny-content", {"files": shiny_app_files()}
        # )


    @reactive.effect
    @reactive.event(input.show_shiny)
    async def force_shiny_open():
        """open the shiny editor window for watching live changes to the shiny app"""
        # This is the client telling the server to show the shiny panel.
        # This is currently necessary (rather than the client having total
        # control) because the server uses a render.ui to create the shiny
        # iframe.
        if not shiny_panel_visible():
            shiny_panel_visible.set(True)


    @reactive.effect
    @reactive.event(shiny_panel_visible)
    async def send_show_shiny_panel_message():
        if shiny_panel_visible():
            print("reloading iframe")
            await session.send_custom_message(
                "show-shiny-panel",
                {
                    "show": True,
                    "smooth": shiny_panel_visible_smooth_transition(),
                },
            )


    @reactive.calc
    def language():
        return "python"


# Remove any consecutive user or assistant messages. Only keep the last one in a
# sequence. For example, if there are multiple user messages in a row, only keep the
# last one. This is helpful for when the user sends multiple messages in a row, which
# can happen if there was an error handling the previous message.
def remove_consecutive_messages(
    messages: tuple[MessageParam, ...],
) -> tuple[MessageParam, ...]:
    if len(messages) < 2:
        return messages

    new_messages: list[MessageParam] = []
    for i in range(len(messages) - 1):
        if messages[i]["role"] != messages[i + 1]["role"]:
            new_messages.append(messages[i])

    new_messages.append(messages[-1])

    return tuple(new_messages)


def transform_shinyapp_tag_contents_to_filecontents(input: str) -> list[FileContent]:
    """
    Extracts the files and their contents from the <SHINYAPP>...</SHINYAPP> tags in the
    input string.
    """
    # Keep the text between the SHINYAPP tags
    shinyapp_code = re.sub(
        r".*<SHINYAPP AUTORUN=\"[01]\">(.*)</SHINYAPP>.*",
        r"\1",
        input,
        flags=re.DOTALL,
    )
    if shinyapp_code.startswith("\n"):
        shinyapp_code = shinyapp_code[1:]

    # Find each <FILE NAME="...">...</FILE> tag and extract the contents and file name
    file_contents: list[FileContent] = []
    for match in re.finditer(r"<FILE NAME=\"(.*?)\">(.*?)</FILE>", input, re.DOTALL):
        name = match.group(1)
        content = match.group(2)
        if content.startswith("\n"):
            content = content[1:]
        file_contents.append({"name": name, "content": content, "type": "text"})

    return file_contents


def transform_messages_to_chatlas_content_format(
    messages: list[MessageParam] | tuple[MessageParam, ...],
) -> Content:
    content = ContentText(text="")

    # concat the most recent user and assistant messages
    user = ""
    assistant = ""
    for msg in reversed(messages):
        c = msg["content"]
        if not isinstance(c, str):
            raise ValueError(
                "Messages must be strings, but got a non-string content: "
                + str(c)
            )

        if msg["role"] == "user" and user == "":
            user = c
        elif msg["role"] == "assistant" and assistant == "":
            assistant = c

        if user != "" and assistant != "":
            break

    content.text = "\n".join([assistant, user])
    return content


app = App(app_ui, server)
