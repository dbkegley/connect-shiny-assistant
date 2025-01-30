### Start the app

> Do not use `--reload` when starting the assistant app because the embedding shiny app
> reload will also cause the parent app to reload, which clears the shiny sessions state and
> chat history in the browser.

`shiny run ./app.py`

### Deploy

```
rsconnect deploy shiny \
--title "Connect Shiny Assistant" \
-n local \
-E ANTHROPIC_API_KEY \
--exclude __pycache__ \
--exclude shiny-app-bundle \
--exclude shiny-app-bundle.tar.gz ./
```
