from shiny import App, render, ui
import numpy as np
import matplotlib.pyplot as plt

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_slider("bins", "Number of bins", min=1, max=50, value=30),
    ),
    ui.card(
        ui.output_plot("histogram"),
    ),
)

def server(input, output, session):
    @render.plot
    def histogram():
        # Generate random data that looks roughly like Old Faithful eruptions
        rng = np.random.default_rng(0)
        eruptions = np.concatenate([
            rng.normal(2, 0.5, 100),
            rng.normal(4.5, 0.5, 100)
        ])

        fig, ax = plt.subplots()
        ax.hist(eruptions, bins=input.bins(), density=True)
        ax.set_xlabel("Eruption duration (minutes)")
        ax.set_ylabel("Density")
        ax.set_title("Histogram of Old Faithful eruptions")

app = App(app_ui, server)
