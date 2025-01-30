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
