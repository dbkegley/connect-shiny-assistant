Connect Shiny Assistant
===============

> Do not try to deploy this application to a real Connect server. It will not work.

This repository contains code for Connect Shiny Assistant. It is a modified version of the
original [`shiny-assistant`](https://github.com/posit-dev/shiny-assistant) but designed to run
on a Posit Connect server rather than running the shiny applications in a browser with WASM/ShinyLive.

This project is built on top of many of the open source tools provided by Posit PBC:
- <https://github.com/posit-dev/shiny-assistant>
- <https://github.com/posit-dev/py-shiny>
- <https://github.com/posit-dev/chatlas>
- <https://github.com/posit-dev/posit-sdk-py>

### Limitations (there are many):

- This version of the assistant is single-tenant. Don't try to edit more than 1 deployed application at a time.
  - This means that if this app is deployed to a Connect server then only 1 person per can interact with it at a time.
- Only supports Shiny for Python, don't try to run R.
- Modifications to the requirements.txt wont be reflected during local editing
  - The dependencies of the shiny app being edited must also be installed in _this apps_ runtime environment
- All sub-processes run on `localhost:8989` via the following command: `shiny run -r --host 0.0.0.0 --port 8989 ./app.py`
  - This means that your browser must be able to reach `$CONNECT_HOST:8989` on `localhost:8989` in order for the
    iframe to load.
- You must convince the LLM to print the source code in order to open the editor iframe
