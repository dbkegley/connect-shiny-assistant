// =====================================================================================
// Set up listeners for messages from server
// =====================================================================================

function chatMessagesContainer() {
  return document.getElementById("ui_chat");
}

Shiny.initializedPromise.then(() => {
  // When the user clicks on the send button, request the latest version of the files
  // from the shiny iframe. This communication is async, so the file contents will
  // arrive later on the server side than the user chat message.
  messageTriggerCounter = 0;
  chatMessagesContainer().addEventListener(
    "shiny-chat-input-sent",
    async (e) => {
      // We don't need this because the input is coming from files on the server, not from the iframe on the client
      //
      // const fileContents = await requestFileContentsFromWindow();
      // Shiny.setInputValue("editor_code", fileContents, {
      //   priority: "event",
      // });
      // This can be removed once we fix
      // https://github.com/posit-dev/py-shiny/issues/1600
      Shiny.setInputValue("message_trigger", messageTriggerCounter++);
    }
  );

  // Receive custom message with app code and send to the shiny panel.
  Shiny.addCustomMessageHandler("set-shiny-content", async (message) => {
    // It's critical that we NOT await ensureShinyPanel from within async
    // custom message handlers. You will get hangs because
    // ensureShinyPanel will not resolve until the shiny panel is
    // ready, but for that to happen, a new custom message must be sent from
    // the server back to the client, which will not be handled because the
    // await holds up the message handler loop.
    //
    // Instead, we handle the promise without awaiting it directly.
    ensureShinyPanel().then(() => {
      sendFileContentsToWindow(message.files);
    });
  });

  // Receive custom message to show the shiny panel
  Shiny.addCustomMessageHandler("show-shiny-panel", (message) => {
    if (message.show === true) {
      showShinyPanel(message.smooth);
    }
  });

  Shiny.addCustomMessageHandler("reload-shiny-panel", (message) => {
    console.log("reloading iframe")
    document.getElementById('shiny-panel').src = "http://localhost:8989";
  });
});

// Listener for "Run code" buttons.
document.addEventListener("click", async (e) => {
  if (e.target.matches(".run-code-button")) {
    await ensureShinyPanel();
    sendThisShinyappToWindow(e.target);
  }
});

// =====================================================================================
// Functions for sending/requesting files from shiny panel
// =====================================================================================

// This should be called from a button inside of the .assistant-shinyapp div. It will
// send the files inside of that div to the shiny panel.
function sendThisShinyappToWindow(buttonEl) {
  const shinyappTag = buttonEl.closest(".assistant-shinyapp");
  const fileTags = shinyappTag.querySelectorAll(".assistant-shinyapp-file");

  const files = Array.from(fileTags).map((fileTag) => {
    return {
      name: fileTag.querySelector(".filename").innerText,
      content: fileTag.querySelector("pre").textContent,
      type: "text",
    };
  });

  sendFileContentsToWindow(files);
}

function sendFileContentsToWindow(fileContents) {
  document.getElementById("shiny-panel").contentWindow.postMessage(
    {
      type: "setFiles",
      files: fileContents,
    },
    "*"
  );
}

async function requestFileContentsFromWindow() {
  const shinyPanel = document.getElementById("shiny-panel");
  if (shinyPanel === null) {
    return [];
  }

  const reply = await postMessageAndWaitForReply(
    document.getElementById("shiny-panel").contentWindow,
    { type: "getFiles" }
  );

  return reply;
}

function postMessageAndWaitForReply(targetWindow, message) {
  return new Promise((resolve) => {
    const channel = new MessageChannel();

    channel.port1.onmessage = (event) => {
      resolve(event.data);
    };

    targetWindow.postMessage(message, "*", [channel.port2]);
  });
}

// =====================================================================================
// Code for saving/loading language switch state to localStorage
// =====================================================================================

const LANGUAGE_INPUT_ID = "language_switch";
const VERBOSITY_INPUT_ID = "verbosity";

$(document).on("shiny:sessioninitialized", function() {
  // Checkbox state is stored as a string in localstorage
  const languageSavedState = localStorage.getItem(LANGUAGE_INPUT_ID) === "true";
  if (languageSavedState !== null) {
    setInputValue(LANGUAGE_INPUT_ID, languageSavedState);
  }

  const verbositySavedState = localStorage.getItem(VERBOSITY_INPUT_ID);
  if (verbositySavedState !== null) {
    setInputValue(VERBOSITY_INPUT_ID, verbositySavedState);
  }
});

$(document).on("shiny:inputchanged", function(e) {
  if ([LANGUAGE_INPUT_ID, VERBOSITY_INPUT_ID].includes(e.name)) {
    localStorage.setItem(e.name, e.value);
  }
});

function setInputValue(inputId, value) {
  const el = document.getElementById(inputId);
  if (!el) {
    console.error("Element with id '" + inputId + "' not found");
    return;
  }
  const binding = $(el).data("shiny-input-binding");
  binding.setValue(el, value);
  $(el).trigger("change");
}

// =====================================================================================
// Recovery code
// =====================================================================================

// Client mirror of server side chat history state
// let chat_history = [];
//
// // Server sends this on new user input or assistant response
// Shiny.addCustomMessageHandler("sync-chat-messages", (msg) => {
//   chat_history.push(...msg.messages);
// });
//
// $(document).on("shiny:disconnected", async () => {
//   // On disconnect, we save all the state needed for restoration to the URL hash
//   // and update the URL immediately. This way, the user can either hit Reload,
//   // or click the Reconnect button, and either way they'll get back to the same
//   // state.
//   //
//   // The restore state starts out as two pieces of JSON that look like:
//   //
//   // chat_history =
//   //   [
//   //     { "role": "user", "content": "Hello" },
//   //     { "role": "assistant", "content": "Certainly! I can help you with that." }
//   //   ];
//   //
//   // files =
//   //   [
//   //     { "name": "app.py", "content": "print('Hello, world!')" }
//   //   ]
//   // }
//   //
//   // Each value is JSONified, base64 encoded, and then turned into query string
//   // pairs. The final URL looks like:
//   // #chat_history=<base64>&files=<base64>
//
//   // We can save the chat history immediately, since we already have the data.
//   // Go ahead and do that, in case something goes wrong with the (much more
//   // complicated) process to get the file data.
//   let hash =
//     "#chat_history=" +
//     encodeURIComponent(encodeToBase64(JSON.stringify(chat_history)));
//   window.location.hash = hash;
//
//   try {
//     // If we successfully get the code from the shiny panel, we'll add that
//     // to the hash as well. The shiny panel may not exist, as it doesn't get
//     // created until the assistant generates some code.
//     if (document.getElementById("shiny-panel")) {
//       const fileContents = await requestFileContentsFromWindow();
//       hash +=
//         "&files=" +
//         encodeURIComponent(encodeToBase64(JSON.stringify(fileContents.files)));
//     }
//   } catch (e) {
//     console.error("Failed to get file contents from shiny panel", e);
//   }
//
//   if (explicitLeftWidth !== null) {
//     hash += `&leftWidth=${explicitLeftWidth}`;
//   }
//
//   window.location.hash = hash;
//
//   // Now that we're done updating the hash, we can show the reconnect modal to
//   // encourage the user to reconnect.
//   const template = document.querySelector("template#custom_reconnect_modal");
//   const clone = document.importNode(template.content, true);
//   document.body.appendChild(clone);
// });

// $(document).on("click", "#custom-reconnect-link", () => {
//   window.location.reload();
// });

// const shinyReadyPromise = new Promise((resolve) => {
//   window.addEventListener("message", (event) => {
//     if (event.data.type === "shinyReady") {
//       resolve();
//     }
//   });
// });
//
// const domContentLoadedPromise = new Promise((resolve) => {
//   document.addEventListener("DOMContentLoaded", resolve);
// });
//
// const shinyConnectedPromise = new Promise((resolve) => {
//   $(document).on("shiny:connected", resolve);
// });
//
// // Drop "#" from hash
// let hash = window.location.hash?.replace(/^#/, "");
// const params = new URLSearchParams(hash || "");
//
// // Now restore shiny file contents from window.location.hash, if any. (We
// // don't need to worry about restoring the chat history here; that's being
// // handled by the server, which always has access to the initial value of
// // window.location.hash.)
// async function restoreFileContents() {
//   if (params.has("files") && params.get("files")) {
//     const files = JSON.parse(
//       decodeFromBase64(decodeURIComponent(params.get("files")))
//     );
//     // Wait for shiny to come online
//     await shinyReadyPromise;
//     if (files.length > 0) {
//       console.log(`Restoring ${files.length} file(s)`);
//     }
//     sendFileContentsToWindow(files);
//   }
// }
//
// async function restoreSidebarSize() {
//   await domContentLoadedPromise;
//   if (params.has("leftWidth")) {
//     const leftWidth = parseInt(params.get("leftWidth"));
//     updateLayout(leftWidth);
//   }
// }
//
// async function restore() {
//   await Promise.all([
//     restoreFileContents(),
//     restoreSidebarSize(),
//     // Wait for shiny to connect before clearing the hash, otherwise the
//     // server won't have the chat history when it needs it
//     shinyConnectedPromise,
//   ]);
//   window.location.hash = "";
// }
//
// restore().catch((err) => {
//   console.error("Failed to restore", err);
// });

// =====================================================================================
// Unicode-aware base64 encoding/decoding
// =====================================================================================

function encodeToBase64(str) {
  const encoder = new TextEncoder();
  const uint8Array = encoder.encode(str);
  return btoa(String.fromCharCode.apply(null, uint8Array));
}

function decodeFromBase64(base64) {
  const binaryString = atob(base64);
  const uint8Array = Uint8Array.from(binaryString, (char) =>
    char.charCodeAt(0)
  );
  const decoder = new TextDecoder();
  return decoder.decode(uint8Array);
}

// =====================================================================================
// Quick and dirty sidebar drag resize
// =====================================================================================

const MIN_WIDTH = "10vw";
const MAX_WIDTH = "90vw";
let explicitLeftWidth = null;

function updateLayout(leftWidth) {
  document
    .querySelector(".bslib-sidebar-layout")
    .style.setProperty(
      "--_sidebar-width",
      `max(min(${leftWidth}px, ${MAX_WIDTH}), ${MIN_WIDTH})`
    );
  explicitLeftWidth = leftWidth;
}

document.addEventListener("DOMContentLoaded", () => {
  const resizer = document.querySelector(".sidebar-resizer");

  const handlePointerMove = (e) => {
    const leftWidth = e.clientX;
    updateLayout(leftWidth);
  };

  const handlePointerUp = (e) => {
    resizer.releasePointerCapture(e.pointerId);
    document.removeEventListener("pointermove", handlePointerMove);
    document.removeEventListener("pointerup", handlePointerUp);
  };

  const handlePointerDown = (e) => {
    resizer.setPointerCapture(e.pointerId);
    document.addEventListener("pointermove", handlePointerMove);
    document.addEventListener("pointerup", handlePointerUp);
  };

  resizer.addEventListener("pointerdown", handlePointerDown);
});

/**
 * Call from anywhere to ensure that the shiny panel is shown and ready.
 */
async function ensureShinyPanel() {
  Shiny.setInputValue("show_shiny", true);
  await shinyReadyPromise;
}

function showShinyPanel(smooth) {
  const el = document.querySelector(".bslib-sidebar-layout");
  el.classList.remove("chat-full-width");

  if (smooth) {
    el.classList.add("sidebar-smooth-transition");
    setTimeout(() => {
      el.classList.remove("sidebar-smooth-transition");
    }, 500);
  }

  // reload the iframe when it opens because the iframe is created before
  // the shiny process starts
  document.getElementById('shiny-panel').src = "http://localhost:8989";

  // document
  //   .querySelector(".bslib-sidebar-layout")
  //   .style.setProperty("--_sidebar-width", defaultSidebarWidth);
}

// // =====================================================================================
// // Close popover when clicking outside
// // =====================================================================================
//
// function getTriggerElement(popoverElement) {
//   // Get all potential trigger elements
//   const triggers = document.querySelectorAll('[data-bs-toggle="popover"]');
//
//   // Iterate through triggers to find the one that matches our popover
//   for (let trigger of triggers) {
//     const popoverInstance = bootstrap.Popover.getInstance(trigger);
//     if (popoverInstance && popoverInstance.tip === popoverElement) {
//       return trigger;
//     }
//   }
//
//   // If no matching trigger is found
//   return null;
// }
//
// document.addEventListener("click", (e) => {
//   const popovers = document.querySelectorAll(".popover");
//   popovers.forEach((popover) => {
//     if (!popover.contains(e.target)) {
//       const trigger = getTriggerElement(popover);
//       if (trigger && !trigger.contains(e.target)) {
//         const popoverInstance = bootstrap.Popover.getInstance(trigger);
//         if (popoverInstance) {
//           popoverInstance.hide();
//         }
//       }
//     }
//   });
// });
//
// setTimeout(() => {
//   var popoverTriggerList = Array.from(
//     document.querySelectorAll('[data-bs-toggle="popover"]')
//   );
//
//   var popoverList = popoverTriggerList.map(function(popoverTriggerEl) {
//     // Only initialize popovers that haven't already be initialized (a bslib popover
//     // would already be initalized by this point, and re-initializing would break it).
//     if (bootstrap.Popover.getInstance(popoverTriggerEl) === null) {
//       return new bootstrap.Popover(popoverTriggerEl);
//     }
//   });
// }, 1000);
