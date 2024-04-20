import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import matplotlib.pyplot as plt
import matplotlib
import seaborn as sns
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, FileResponse
import io
import base64

app = FastAPI()

documents = [
    "Services", "Furniture", "Cottage and garden", "Home and Decor",
    "Lighting", "Plumbing", "Renovation and finishing", "Appliances",
    "Payment of debt", "Products without a category", "1+1=discount",
    "Plumbing///Water supply", "Lighting///Chandeliers", "Lighting///Fixtures",
    "Lighting///Sconces and lights", "Lighting///Table lamps",
    "Lighting///Floor lamps", "Lighting///Spots", "Lighting///Track systems",
    "Lighting///Office lighting", "Lighting///Street lighting",
    "Lighting///LED backlight", "Lighting///Light bulbs",
    "Lighting///Accessories", "Home and Decor///Bedding",
    "Home and Decor///Bed linen", "Home and Decor///Tableware",
    "Home and Decor///Organization and storage", "Home and Decor///Textile",
    "Home and Decor///Household goods", "Home and decor///Covers",
    "Furniture///Sofa"
]

vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(documents)

cosine_sim_matrix = cosine_similarity(X)


@app.get("/", response_class=HTMLResponse)
async def read_root():
  fig, ax = plt.subplots(figsize=(12, 10), dpi=150)
  sns.heatmap(cosine_sim_matrix,
              annot=True,
              fmt=".2f",
              cmap='coolwarm',
              xticklabels=documents,
              yticklabels=documents,
              ax=ax,
              cbar=True,
              cbar_kws={"shrink": .8},
              linewidths=0.05,
              linecolor='blue',
              annot_kws={"size": 8})
  ax.set_title('Cosine Similarity Matrix', fontsize=18, fontweight='bold')
  plt.xticks(rotation=45, ha="right", fontsize=8)
  plt.yticks(fontsize=8)

  buf = io.BytesIO()
  fig.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.5)
  buf.seek(0)
  plt.close(fig)

  base64_img = base64.b64encode(buf.read()).decode('utf-8')
  html = f"<html><body><div style='text-align: center;'><h1>Cosine Similarity Matrix</h1><img src='data:image/png;base64,{base64_img}' style='margin: auto; display: block;'/></div></body></html>"
  return HTMLResponse(content=html, status_code=200)


@app.get("/download")
async def download_image():
  fig, ax = plt.subplots(figsize=(12, 10), dpi=150)
  sns.heatmap(cosine_sim_matrix,
              annot=True,
              fmt=".2f",
              cmap='coolwarm',
              xticklabels=documents,
              yticklabels=documents,
              ax=ax,
              cbar=True,
              cbar_kws={"shrink": .8},
              linewidths=0.05,
              linecolor='blue',
              annot_kws={"size": 8})
  ax.set_title('Cosine Similarity Matrix', fontsize=18, fontweight='bold')
  plt.xticks(rotation=45, ha="right", fontsize=8)
  plt.yticks(fontsize=8)

  buf = io.BytesIO()
  fig.savefig(buf, format='png')
  plt.close(fig)
  buf.seek(0)
  return Response(content=buf.getvalue(),
                  media_type="image/png",
                  headers={
                      "Content-Disposition":
                      "attachment;filename=cosine_similarity_matrix.png"
                  })
