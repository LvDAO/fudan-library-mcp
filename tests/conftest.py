import pytest


@pytest.fixture
def record():
    # Synthetic data shaped like the live Primo response; no publisher text or tokens.
    return {
        "context": "PC",
        "pnx": {
            "control": {"recordid": ["TN_test_123"]},
            "display": {
                "title": ["<h>测试</h> Graph &amp; Text"],
                "description": ["A synthetic abstract with <b>evidence</b> and x < 2."],
                "snippet": ["... matched <h>term</h> ..."],
                "type": ["article"],
                "language": ["eng"],
                "source": ["Example <img src='http://bad.invalid/a.png'> Database"],
            },
            "addata": {
                "abstract": ["A synthetic abstract with <b>evidence</b> and x < 2."],
                "au": ["Li, A", "Wang, B"],
                "date": ["2024-05-21"],
                "doi": ["10.1234/test"],
                "jtitle": ["Example Journal"],
            },
            "search": {"subject": ["Graph methods"]},
            "facets": {"toplevel": ["peer_reviewed", "online_resources", "open_access"]},
            "links": {
                "linktopdf": ["$$Uhttps://publisher.example/paper.pdf$$EPDF$$Gtest"],
                "backlink": ["$$Ujavascript:alert(1)$$Dinvalid"],
            },
        },
        "delivery": {
            "availability": ["fulltext"],
            "link": [
                {"displayLabel": "openurlfulltext", "linkURL": "https://resolver.example/1"},
                {"displayLabel": "thumbnail", "linkURL": "https://image.example/1"},
            ],
        },
    }
