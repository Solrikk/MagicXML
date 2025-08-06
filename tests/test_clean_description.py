import ast
import pathlib
import pytest

# Ensure BeautifulSoup is available; skip tests if not installed
bs4 = pytest.importorskip("bs4")
from bs4 import BeautifulSoup


def load_clean_description():
    """Dynamically load the clean_description function from main.py without importing the whole module."""
    file_path = pathlib.Path(__file__).resolve().parents[1] / "main.py"
    source = file_path.read_text()
    module = ast.parse(source)
    func_node = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "clean_description"
    )
    mod = ast.Module(body=[func_node], type_ignores=[])
    namespace = {"BeautifulSoup": BeautifulSoup}
    exec(compile(mod, filename=str(file_path), mode="exec"), namespace)
    return namespace["clean_description"]


clean_description = load_clean_description()


def test_remove_disallowed_tags():
    input_html = "<div><span>Text</span><p>Paragraph</p></div>"
    expected = "<p>Text</p><p>Paragraph</p>"
    assert clean_description(input_html) == expected


def test_wrap_plain_text_in_p_tags():
    assert clean_description("Just text") == "<p>Just text</p>"


def test_preserve_p_and_br_tags():
    input_html = "<p>Hello<br>world</p>"
    expected = "<p>Hello<br/>world</p>"
    assert clean_description(input_html) == expected
