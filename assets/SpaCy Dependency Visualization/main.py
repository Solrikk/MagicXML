from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
import spacy
from spacy import displacy
from sklearn.feature_extraction.text import TfidfVectorizer
import pandas as pd

app = FastAPI()

try:
  nlp = spacy.load("en_core_web_sm")
except:
  from spacy.cli.download import download
  download("en_core_web_sm")
  nlp = spacy.load("en_core_web_sm")


def compute_tfidf(text):
  tfidf_vectorizer = TfidfVectorizer()
  vectors = tfidf_vectorizer.fit_transform([text])
  feature_names = tfidf_vectorizer.get_feature_names_out()
  scores = vectors.T.toarray()
  df_scores = pd.DataFrame(scores, index=feature_names, columns=["TF-IDF"])
  df_scores = df_scores.sort_values(by=["TF-IDF"], ascending=False)
  return df_scores.head(10).to_html()


@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
  html_content = """
    <html>
        <body>
            <form action="/analyze/" method="post">
                <textarea name="text" rows="10" cols="50"></textarea>
                <button type="submit">Analyze</button>
            </form>
        </body>
    </html>
    """
  return HTMLResponse(content=html_content)


@app.post("/analyze/", response_class=HTMLResponse)
async def analyze_text(text: str = Form(...)):
  doc = nlp(text)

  html_dep = displacy.render(doc, style="dep", page=False)

  tfidf_html = compute_tfidf(text)

  combined_html = f"<div>{html_dep}</div><div>{tfidf_html}</div>"
  return HTMLResponse(content=combined_html)
