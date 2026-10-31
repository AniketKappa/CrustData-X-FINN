import pytest

from finn.people import Person, BioLine, parse_change, sentences_about, wikipedia_match, write_brief
from finn.providers.news import is_noise


@pytest.mark.parametrize("h,inc,out", [
    ("Trent names Bahram Vakil chairman as Noel Tata to step down after nearly three decades", "Bahram Vakil", "Noel Tata"),
    ("Noel Tata to retire as Trent chairman on Nov 11; Bahram Vakil to take over", "Bahram Vakil", "Noel Tata"),
    ("Who Is Bahram Vakil? All About Noel Tata's Successor As Trent Chairman", "Bahram Vakil", None),
    ("Info Edge CEO Hitesh Oberoi to step down after 27 years, Sanjeev Bikhchandani to take over", "Sanjeev Bikhchandani", "Hitesh Oberoi"),
    ("Ola Electric Mobility Appoints Deepak Rastogi as CFO; Harish Abichandani Steps Down", "Deepak Rastogi", "Harish Abichandani"),
    ("Appointment of Mr. Sunil Upadhyay as Chief Financial Officer of the Company", "Sunil Upadhyay", None),
    ("Capri Global Capital Announces Resignation of CEO Monu Ratra", None, "Monu Ratra"),
    ("Trent Q2 profit rises 25% as Zudio, Star grow", None, None),
])
def test_parse_change(h, inc, out):
    c = parse_change(h, "Trent Ltd")
    assert (c.incoming, c.outgoing) == (inc, out)


def test_sentences_about_keeps_bio_sentences_only():
    text = ("Bahram Vakil is a co-founder of AZB & Partners. Shares rose 2% today. "
            "He previously served on the boards of Voltas and Larsen & Toubro. The weather was fine.")
    out = sentences_about(text, "Bahram Vakil")
    assert out == ["Bahram Vakil is a co-founder of AZB & Partners.",
                   "He previously served on the boards of Voltas and Larsen & Toubro."]


def test_wikipedia_requires_same_person():
    good = {"type": "standard", "extract": "Sanjeev Bikhchandani is an Indian entrepreneur who founded Info Edge."}
    assert wikipedia_match(good, "Sanjeev Bikhchandani", "Info Edge (India) Ltd")
    assert wikipedia_match({"type": "disambiguation", "extract": "x"}, "A B", "C") is None
    assert wikipedia_match({"type": "standard", "extract": "Bahram is a Persian name."}, "Bahram Vakil", "Trent Ltd") is None


def test_write_brief_requires_citations():
    p = Person(name="X Y", role="CFO", company="Co", symbol="CO", lines=[BioLine(text="X Y joined in 2010.", source="s")])
    assert write_brief(p, None) is None
    assert write_brief(p, lambda prompt: "X Y joined Co in 2010 [1]. He is a chartered accountant [1].") is not None
    assert write_brief(p, lambda prompt: "X Y is a renowned leader. Nobody knows more.") is None   # uncited -> rejected


@pytest.mark.parametrize("h,noise", [
    ("Reliance Industries Ltd. Share Price, Stock Price - NSE/BSE Live", True),
    ("Stocks To Watch Today: Dixon Tech, Syrma SGS, Sun Pharma, Wipro, Trent Among Others", True),
    ("Buy Vedanta; target of Rs 330: ICICI Securities", True),
    ("HDFC Bank, ITC, HDFC Life, Nestle, Britannia, TaMo PV hit 52-week lows", True),
    ("Noel Tata to retire as chairman of Trent on Nov 11; Bahram Vakil to take over", False),
    ("Axis Trustee gives Yes Bank three working days to restore ₹8,415 crore AT1 bonds", False),
])
def test_noise(h, noise):
    assert is_noise(h) is noise


def test_news_clustered_and_management_person(pipe):
    d = pipe.digest(168)
    keys = [(i.symbol, i.category, i.filed_at.date()) for i in d.news]
    assert len(keys) == len(set(keys))                       # one story per company, type and day
    deal = next(i for i in d.news if i.category == "M&A")
    assert len(deal.related) == 0 or deal.related[0]["publisher"]
    mgmt = next(i for i in d.news if i.category == "management_change")
    assert mgmt.person is None or mgmt.person["name"] or mgmt.person["outgoing"]
