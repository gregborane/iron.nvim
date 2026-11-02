# Send one cell at a time from an image-enabled Iron Python REPL.
# For Foot: image = { protocol = "sixel", cell_width = 8, cell_height = 16 }
# Match the pixel dimensions to your terminal font; restart the REPL after setup.
# Install matplotlib/Pillow/plotly in the REPL's Python environment.
# Kaleido is NOT needed: interactive Plotly figures open directly in a browser.

# %% Matplotlib: static plot inside the REPL
import matplotlib.pyplot as plt

plt.plot([1, 3, 2, 5, 4])
plt.title("Matplotlib: inline plot")
plt.show()

# %% Pillow: static image inside the REPL, no external viewer
from PIL import Image, ImageDraw

img = Image.new("RGB", (300, 150), "white")
draw = ImageDraw.Draw(img)
draw.rectangle([20, 20, 140, 130], fill="red")
draw.ellipse([160, 20, 280, 130], fill="blue")
img.show()

# %% CMYK images are converted for inline PNG output
Image.new("CMYK", (200, 100), (0, 255, 255, 0)).show()

# %% Plotly: interactive chart in the default browser, no static preview
import plotly.graph_objects as go

pfig = go.Figure(go.Scatter(y=[1, 3, 2, 5, 4], mode="lines+markers"))
pfig.update_layout(title="Plotly: browser chart with hover and zoom")
pfig.show()

# %% IPython/Jupyter only: bare figure also opens the browser
pfig

# %% Explicit static Plotly export (optional; needs Kaleido + Chrome/Chromium)
# from iron_image import display
# display(pfig.to_image(format="png", width=900, height=500))
