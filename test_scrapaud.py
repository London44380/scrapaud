#!/usr/bin/env python3
"""Tests hors-ligne de scrapaud (aucun accès Internet) : python3 -m unittest -v test_scrapaud"""
import http.server
import io
import json
import os
import re
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import warnings
import zipfile

warnings.simplefilter("ignore", ResourceWarning)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scrapaud as s  # noqa: E402


def setup_args(*argv):
    s.ARGS, _ = s.parse_args(["-q", "x", "--quiet", "--no-cache", "--no-searx", "--allow-private", "--delay", "0", *argv])
    s._opener = s.build_opener(None)
    s._dead.clear()
    return s.ARGS


class MiniServer:
    """Serveur HTTP local : dict chemin -> (content-type, corps bytes)."""

    def __init__(self, pages):
        pages_ = pages

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path in pages_ and pages_[self.path][0] == "302":     # redirection vers l'URL indiquée
                    self.send_response(302)
                    self.send_header("Location", pages_[self.path][1].replace("{BASE}", f"http://127.0.0.1:{self.server.server_port}"))
                    self.end_headers()
                elif self.path in pages_:
                    ct, body = pages_[self.path]
                    if body == "{ECHO}":                                         # renvoie les en-têtes reçus
                        body = f"cookie={self.headers.get('Cookie', '')};token={self.headers.get('X-Token', '')}"
                    body = body if isinstance(body, bytes) else body.encode()
                    body = body.replace(b"{BASE}", f"http://127.0.0.1:{self.server.server_port}".encode())
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


class UrlAndMerge(unittest.TestCase):
    def setUp(self):
        setup_args()

    def test_norm_url(self):
        a = s.norm_url("https://www.Example.com/a/?utm_source=x&b=2&a=1#frag")
        b = s.norm_url("http://example.com/a?a=1&b=2")
        self.assertEqual(a, b)
        self.assertNotEqual(s.norm_url("https://p.com/AbC"), s.norm_url("https://p.com/abc"))  # casse préservée
        self.assertEqual(s.norm_url("https://x.org/index.html"), s.norm_url("https://x.org/"))

    def test_rrf_merge_ranks_multi_engine_higher(self):
        r = lambda u, sn="": {"title": u, "url": u, "snippet": sn}
        merged = s.rrf_merge([("a", [r("https://x.com/1"), r("https://y.com/2")]),
                              ("b", [r("https://y.com/2", "snippet plus long"), r("https://z.com/3")])])
        self.assertEqual(merged[0]["url"], "https://y.com/2")          # trouvé par 2 moteurs
        self.assertEqual(merged[0]["engine"], "a,b")
        self.assertEqual(merged[0]["snippet"], "snippet plus long")    # garde le meilleur extrait
        self.assertEqual(len(merged), 3)

    def test_rrf_dedup_variants(self):
        r = lambda u: {"title": "t", "url": u, "snippet": ""}
        merged = s.rrf_merge([("a", [r("https://www.x.com/p?utm_source=1")]), ("b", [r("http://x.com/p/")])])
        self.assertEqual(len(merged), 1)


class Parsing(unittest.TestCase):
    def setUp(self):
        setup_args()

    def test_page_parser(self):
        html = """<html><head><title> Ma  page </title><meta name="description" content="desc">
        <link rel="alternate" type="application/rss+xml" href="/feed.xml"></head><body>
        <nav class="main-menu"><ul><li>Menu1</li><li>Menu2</li><li>Menu3</li></ul></nav>
        <ul><li>pomme</li><li>poire</li><li>kiwi</li><li>fraise</li></ul>
        <pre>ligne1\nligne2\nligne3</pre>
        <table><tr><th>N</th></tr><tr><td>Paris</td><td>75</td></tr></table>
        <a href="/x?y=1">Lien</a><a href="javascript:void(0)">no</a><img src="/i.png" alt="img">
        <script>var a = "<li>faux</li>";</script></body></html>"""
        p = s.PageParser("https://ex.org/dir/")
        p.feed(html)
        self.assertEqual(p.title.strip(), "Ma  page")
        self.assertEqual(p.description, "desc")
        self.assertEqual(p.feeds, ["https://ex.org/feed.xml"])
        self.assertEqual([l["url"] for l in p.links], ["https://ex.org/x?y=1"])
        self.assertEqual(p.images[0]["url"], "https://ex.org/i.png")
        self.assertIn("pomme", p.items)
        self.assertNotIn("faux", " ".join(p.items))
        self.assertEqual(p.pre[0].splitlines()[0], "ligne1")
        ui = [ui for ui, _ in p.lists]
        self.assertEqual(ui, [True, False])            # le menu <nav> est signalé comme interface
        self.assertEqual(p.tables[0][-1], ["Paris", "75"])

    def test_bing_real_url_decoding(self):
        import base64
        u = base64.urlsafe_b64encode(b"https://exemple.org/page?a=1").decode().rstrip("=")
        self.assertEqual(s._bing_real_url(f"https://www.bing.com/ck/a?!&p=abc&u=a1{u}&ntb=1"), "https://exemple.org/page?a=1")

    def test_ddg_parser(self):
        html = ('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fex.org%2Fa&rut=1">Titre <b>A</b></a>'
                '<a class="result__snippet">Extrait</a>'
                '<a class="result__a" href="//duckduckgo.com/y.js?ad=1">Pub</a>')
        p = s.DDGParser()
        p.feed(html)
        self.assertEqual(p.results[0]["url"], "https://ex.org/a")
        self.assertEqual(p.results[0]["title"], "Titre A")

    def test_ahmia_parser(self):
        page1 = '<input type="hidden" name="tk" value="42">'
        page2 = ('<li class="result"><h4><a href="/search/redirect?search_term=w&amp;redirect_url=http://abcdefghij234567.onion/">'
                 'Hidden <b>Wiki</b></a></h4><p>Une <i>description</i></p></li>'
                 '<li class="result"><h4><a href="/search/redirect?redirect_url=http://clear.example.com/">x</a></h4></li>')
        calls = []
        orig = s.fetch
        s.fetch = lambda url, **kw: (calls.append(url), ((page2 if "tk=42" in url else page1), url, "text/html"))[1]
        try:
            res = s.eng_ahmia("wiki", 1)
        finally:
            s.fetch = orig
        self.assertEqual(res, [{"title": "Hidden Wiki", "url": "http://abcdefghij234567.onion/", "snippet": "Une description"}])
        self.assertIn("tk=42", calls[-1])

    def test_arxiv_parser(self):
        atom = ("<?xml version='1.0'?><feed xmlns=\"http://www.w3.org/2005/Atom\"><entry><id>http://arxiv.org/abs/1</id>"
                "<published>2024-01-01T00:00:00Z</published><title>Un  titre\n deux lignes</title><summary>Résumé</summary></entry></feed>")
        orig = s.fetch
        s.fetch = lambda url, **kw: (atom, url, "application/atom+xml")
        s._arxiv_last[0] = 0
        try:
            res = s.eng_arxiv("post quantum", 1)
        finally:
            s.fetch = orig
        self.assertEqual(res[0]["title"], "Un titre deux lignes")


class Pastes(unittest.TestCase):
    def setUp(self):
        setup_args()

    def test_paste_raw_mapping(self):
        cases = {
            "https://pastebin.com/AbCdEfGh": "https://pastebin.com/raw/AbCdEfGh",
            "https://pastebin.com/u/foo": None,
            "https://pastebin.com/archive": None,
            "https://dpaste.com/ABC123": "https://dpaste.com/ABC123.txt",
            "https://rentry.co/abcd": "https://rentry.co/abcd/raw",
            "https://paste.ee/p/AbC": "https://paste.ee/r/AbC",
            "https://bpa.st/ABCD": "https://bpa.st/raw/ABCD",
            "https://mclo.gs/AbC123": "https://api.mclo.gs/1/raw/AbC123",
            "https://hackmd.io/@user/slug": "https://hackmd.io/@user/slug/download",
            "https://pastes.dev/AbC": "https://api.pastes.dev/AbC",
            "https://gitlab.com/-/snippets/123456": "https://gitlab.com/-/snippets/123456/raw",
            "https://ideone.com/aBcDe": "https://ideone.com/plain/aBcDe",
            "https://example.com/a": None,
        }
        for url, expected in cases.items():
            self.assertEqual(s.paste_raw(url), expected, url)

    def test_every_listed_domain_has_a_raw_mapping(self):
        """Un domaine listé sans conversion vers le brut serait cherché pour rien : cohérence liste <-> paste_raw."""
        sample = {"pastebin.com": "https://pastebin.com/AbCdEfGh", "gist.github.com": "https://gist.github.com/u/0123456789abcdef0123456789abcdef",
                  "dpaste.com": "https://dpaste.com/ABC123", "dpaste.org": "https://dpaste.org/abcd", "rentry.co": "https://rentry.co/abcd",
                  "paste.ee": "https://paste.ee/p/AbC", "bpa.st": "https://bpa.st/ABCD", "paste.debian.net": "https://paste.debian.net/1234567/",
                  "paste.rs": "https://paste.rs/abc", "hst.sh": "https://hst.sh/abc", "pastes.dev": "https://pastes.dev/abc",
                  "pastefy.app": "https://pastefy.app/abc", "pastebin.pl": "https://pastebin.pl/view/abc123", "ideone.com": "https://ideone.com/abcde",
                  "gitlab.com": "https://gitlab.com/-/snippets/123", "sprunge.us": "https://sprunge.us/abc", "termbin.com": "https://termbin.com/abc",
                  "hasteb.in": "https://hasteb.in/abc", "paste.helpch.at": "https://paste.helpch.at/abc", "mclo.gs": "https://mclo.gs/AbC123",
                  "hackmd.io": "https://hackmd.io/AbCdEf", "justpaste.it": "https://justpaste.it/abc12", "controlc.com": "https://controlc.com/abc123",
                  "pastelink.net": "https://pastelink.net/abc", "telegra.ph": "https://telegra.ph/x-09-20"}
        self.assertEqual(set(sample), set(s.PASTE_DOMAINS))                # aucune entrée oubliée ni en trop
        self.assertEqual(len(s.PASTE_DOMAINS), len(set(s.PASTE_DOMAINS)))   # pas de doublon
        for dom, url in sample.items():
            self.assertIsNotNone(s.paste_raw(url), dom)
        for dead in ("paste.md-5.net", "hastebin.com"):                      # retirés : le DNS ne résout plus / accès authentifié
            self.assertNotIn(dead, s.PASTE_DOMAINS)

    def test_blob_to_raw(self):
        self.assertEqual(s.to_raw_url("https://github.com/u/r/blob/main/a/b.txt"),
                         "https://raw.githubusercontent.com/u/r/main/a/b.txt")


class TextLists(unittest.TestCase):
    def setUp(self):
        setup_args()

    def test_clean_lines_and_as(self):
        s.ARGS.strip_comments = True
        lines = ["# commentaire", "alpha.example.com", "", "alpha.example.com", "10.0.0.1 gw", "192.168.1.2:8080", "a.b@ex.fr"]
        self.assertEqual(s.clean_lines(lines)[0], "alpha.example.com")
        s.ARGS.text_as = "ips"
        self.assertEqual(s.clean_lines(lines), ["10.0.0.1", "192.168.1.2"])
        s.ARGS.text_as = "ipport"
        self.assertEqual(s.clean_lines(lines), ["192.168.1.2:8080"])
        s.ARGS.text_as = "emails"
        self.assertEqual(s.clean_lines(lines), ["a.b@ex.fr"])

    def test_auto_mode_ignores_menu_and_picks_richest(self):
        html = ("<html><body><nav><ul><li>a</li><li>b</li><li>c</li><li>d</li><li>e</li></ul></nav>"
                "<ul><li>pomme</li><li>poire</li><li>kiwi</li></ul></body></html>")
        srv = MiniServer({"/l.html": ("text/html", html)})
        try:
            self.assertEqual(s.raw_text_lines(srv.url + "/l.html"), ["pomme", "poire", "kiwi"])
        finally:
            srv.close()

    def test_local_file_and_dedup_sort(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("b\na\nb\n")
        try:
            s.ARGS.sort = True
            tl = s.build_textlist([f.name])
            self.assertEqual([i["line"] for i in tl["items"]], ["a", "b"])
        finally:
            os.unlink(f.name)


class Documents(unittest.TestCase):
    def setUp(self):
        setup_args()

    def test_office_formats(self):
        docx = make_zip({"word/document.xml": "<w:p><w:t>Titre</w:t></w:p><w:p><w:t>a@b.fr</w:t><w:tab/><w:t>x</w:t></w:p>"})
        self.assertEqual(s.extract_doc_text(docx, "docx").splitlines(), ["Titre", "a@b.fr\tx", ""][:2] + [])
        xlsx = make_zip({"xl/sharedStrings.xml": "<sst><si><t>alpha</t></si><si><t>b &amp; c</t></si></sst>"})
        self.assertEqual(s.extract_doc_text(xlsx, "xlsx").split(), ["alpha", "b", "&", "c"])
        pptx = make_zip({"ppt/slides/slide10.xml": "<a:p><a:t>Dix</a:t></a:p>", "ppt/slides/slide2.xml": "<a:p><a:t>Deux</a:t></a:p>"})
        self.assertEqual(s.extract_doc_text(pptx, "pptx").split(), ["Deux", "Dix"])   # ordre numérique
        odt = make_zip({"content.xml": "<text:p>Un</text:p><text:h>Deux</text:h>"})
        self.assertEqual(s.extract_doc_text(odt, "odt").split(), ["Un", "Deux"])

    def test_bad_zip_and_kind_detection(self):
        with self.assertRaises(ValueError):
            s.extract_doc_text(b"pas un zip", "docx")
        self.assertEqual(s.doc_kind("https://x.org/a/b.PDF?x=1"), "pdf")
        self.assertIsNone(s.doc_kind("https://x.org/a.html"))
        self.assertEqual(s.sniff_doc_kind("%PDF-1.7 ...", "text/plain"), "pdf")

    @unittest.skipUnless(s.shutil.which("pdftotext"), "pdftotext absent")
    def test_pdf_via_pdftotext(self):
        pdf = (b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
               b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
               b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 10 50 Td (Bonjour PDF) Tj ET\nendstream endobj\n"
               b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\n%%EOF\n")
        self.assertIn("Bonjour PDF", s.extract_doc_text(pdf, "pdf"))

    def test_scrape_document_over_http(self):
        docx = make_zip({"word/document.xml": "<w:p><w:t>voir https://exemple.org/x et jean@ex.fr</w:t></w:p>"})
        srv = MiniServer({"/r.docx": ("application/octet-stream", docx)})
        try:
            s.ARGS._extract = {"links", "items", "emails"}
            pg = s.scrape_page(srv.url + "/r.docx")
            self.assertEqual(pg["doctype"], "docx")
            self.assertEqual(pg["emails"], ["jean@ex.fr"])
            self.assertEqual(pg["links"][0]["url"], "https://exemple.org/x")
        finally:
            srv.close()


class SitemapsAndFeeds(unittest.TestCase):
    def setUp(self):
        setup_args()

    def test_sitemap_index_and_robots_discovery(self):
        sm = '<urlset><url><loc>{BASE}/a</loc><lastmod>2026-01-02</lastmod></url><url><loc>{BASE}/b?x=1&amp;y=2</loc></url></urlset>'
        idx = '<sitemapindex><sitemap><loc>{BASE}/sm.xml</loc></sitemap></sitemapindex>'
        srv = MiniServer({"/sm.xml": ("application/xml", sm), "/idx.xml": ("application/xml", idx),
                          "/robots.txt": ("text/plain", "User-agent: *\nSitemap: {BASE}/idx.xml\n")})
        try:
            urls = s.read_sitemap(srv.url + "/idx.xml")
            self.assertEqual(len(urls), 2)
            self.assertTrue(urls[1]["url"].endswith("/b?x=1&y=2"))   # &amp; décodé
            self.assertEqual(urls[0]["text"], "2026-01-02")
            self.assertEqual(s.discover_sitemaps(srv.url)[0], srv.url + "/idx.xml")   # via robots.txt
            self.assertEqual(len(s.sitemap_page(srv.url)["links"]), 2)
        finally:
            srv.close()

    def test_sitemap_no_xxe_regex_only(self):
        body = '<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><urlset><url><loc>&a;</loc></url></urlset>'
        self.assertEqual(s._loc_blocks(body, "url")[0][0], "&a;")    # jamais résolu, juste du texte

    def test_rss_atom_and_entity_refusal(self):
        rss = ('<?xml version="1.0"?><rss version="2.0"><channel><title>Flux</title><item><title>A &amp; B</title>'
               '<link>http://e.org/1</link><pubDate>Sun, 20 Sep 2026 10:00:00 GMT</pubDate>'
               '<description><![CDATA[<p>Résumé <b>gras</b></p>]]></description></item></channel></rss>')
        pg = s.parse_feed(rss, "http://e.org/f")
        self.assertEqual(pg["entries"][0]["title"], "A & B")
        self.assertEqual(pg["entries"][0]["summary"], "Résumé gras")
        atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title><entry><title>E1</title>'
                '<link href="http://e.org/e1"/><updated>2026-09-19T08:00:00Z</updated></entry></feed>')
        self.assertEqual(s.parse_feed(atom, "u")["entries"][0]["url"], "http://e.org/e1")
        with self.assertRaises(ValueError):
            s.parse_feed('<!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>', "u")

    def test_autodetect_in_scrape_page(self):
        srv = MiniServer({"/f.xml": ("application/rss+xml", '<rss><channel><title>F</title><item><title>x</title><link>http://e.org/x</link></item></channel></rss>')})
        try:
            self.assertEqual(s.scrape_page(srv.url + "/f.xml")["type"], "feed")
        finally:
            srv.close()


class FakeSocks(threading.Thread):
    """Serveur SOCKS5 minimal : enregistre l'hôte demandé puis renvoie une réponse HTTP fixe."""

    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.requested = None
        self.dns_leak_free = True
        self.start()

    def run(self):
        while True:   # la 1re connexion est la sonde de disponibilité de tor_opener() : on l'ignore
            c, _ = self.sock.accept()
            greeting = c.recv(3)
            if greeting:
                break
            c.close()
        c.sendall(b"\x05\x00")
        head = c.recv(4)
        atyp = head[3]
        if atyp == 3:
            n = c.recv(1)[0]
            self.requested = c.recv(n).decode()
        else:
            self.dns_leak_free = False   # le client a résolu le nom lui-même
        c.recv(2)
        c.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        c.recv(4096)
        body = b"bonjour depuis un onion"
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
        c.close()
        self.sock.close()


class Tor(unittest.TestCase):
    def test_socks5_remote_dns_for_onion(self):
        fake = FakeSocks()
        setup_args("--tor-proxy", f"127.0.0.1:{fake.port}")
        s._tor = None
        body, _, _ = s.fetch("http://abcdefghij234567.onion/page", retries=0)
        fake.join(3)
        self.assertEqual(body, "bonjour depuis un onion")
        self.assertEqual(fake.requested, "abcdefghij234567.onion")   # nom transmis à Tor, pas résolu localement
        self.assertTrue(fake.dns_leak_free)
        s._tor = None

    def test_tor_unreachable_message(self):
        setup_args("--tor-proxy", "127.0.0.1:1")
        s._tor = None
        with self.assertRaises(ValueError) as cm:
            s.fetch("http://x.onion/", retries=0)
        self.assertIn("Tor injoignable", str(cm.exception))
        s._tor = None


class CacheAndConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        s.CACHE_DIR = self.tmp
        s.ARGS, _ = s.parse_args(["-q", "x", "--quiet", "--no-searx"])
        s._cache_puts[0] = 0

    def test_roundtrip_ttl_and_trim(self):
        k = s.cache_key("a", 1)
        self.assertIsNone(s.cache_get(k))
        s.cache_put(k, {"x": [1, 2, "é"]})
        self.assertEqual(s.cache_get(k), {"x": [1, 2, "é"]})
        os.utime(os.path.join(self.tmp, k + ".json.gz"), (time.time() - 99999,) * 2)
        self.assertIsNone(s.cache_get(k))                         # expiré
        for i in range(30):
            s.cache_put(s.cache_key("b", i), {"pad": os.urandom(2000).hex()})
        self.assertGreater(s.cache_trim(limit=20000), 0)          # éviction des plus anciens
        self.assertEqual(s.cache_clear() >= 0, True)

    def test_no_cache_flag(self):
        s.ARGS.no_cache = True
        s.cache_put("k", {"a": 1})
        self.assertIsNone(s.cache_get("k"))

    def test_config_file(self):
        cfg = os.path.join(self.tmp, "c.toml")
        with open(cfg, "w") as f:
            f.write('limit = 7\nlang = "en"\nnot-domain = ["spam.com"]\nbogus = 1\n')
        err = io.StringIO()
        old, sys.stderr = sys.stderr, err
        try:
            a, _ = s.parse_args(["--config", cfg, "-q", "x", "--no-searx"])
        finally:
            sys.stderr = old
        self.assertEqual((a.limit, a.lang, a.not_domain), (7, "en", ["spam.com"]))
        self.assertIn("bogus", err.getvalue())
        a, _ = s.parse_args(["--config", cfg, "-q", "x", "--limit", "3", "--no-searx"])
        self.assertEqual(a.limit, 3)                              # la ligne de commande prime


class Engines(unittest.TestCase):
    def setUp(self):
        setup_args()

    def test_dead_engine_skipped_after_block(self):
        calls = []

        def blocked(q, page):
            calls.append(1)
            raise urllib.error.HTTPError("u", 429, "Too Many", {}, None)
        orig = dict(s.ENGINES)
        s.ENGINES["bing"] = blocked
        s.ENGINES["ddg"] = lambda q, p: [{"title": "t", "url": "https://x.org/", "snippet": ""}]
        try:
            self.assertEqual(s.search("q")[0]["url"], "https://x.org/")   # repli sur ddg
            self.assertTrue(s.engine_is_dead("bing"))
            s.search("q2")
            self.assertEqual(len(calls), 1)                              # bing plus réinterrogé
        finally:
            s.ENGINES.clear()
            s.ENGINES.update(orig)
            s._dead.clear()

    def test_all_engines_merge_and_filters(self):
        orig = dict(s.ENGINES)
        r = lambda u: {"title": u, "url": u, "snippet": ""}
        s.ENGINES.update(a=lambda q, p: [r("https://spam.com/1"), r("https://ok.org/1")],
                         b=lambda q, p: [r("https://ok.org/1?utm_source=z")])
        s.ARGS._engines = ["a", "b"]
        s.ARGS.not_domain = ["spam.com"]
        try:
            res = s.search("q")
            self.assertEqual([x["url"] for x in res], ["https://ok.org/1"])
            self.assertEqual(res[0]["engine"], "a,b")
        finally:
            s.ENGINES.clear()
            s.ENGINES.update(orig)

    def test_invalid_args_rejected(self):
        for bad in (["-e", "nimportequoi"], ["-x", "zzz"], ["--grep", "("], ["--paste-sites", "nope.tld"]):
            with self.assertRaises(SystemExit):
                old, sys.stderr = sys.stderr, io.StringIO()
                try:
                    s.parse_args(["-q", "x", "--no-searx", *bad])
                finally:
                    sys.stderr = old


class SelectorLogic(unittest.TestCase):
    def test_toggle_filter_all_invert(self):
        sel = s.Selector(["pomme", "poire", "banane", "kiwi"], ["fruit rouge", "", "jaune", ""])
        sel.toggle()
        self.assertEqual(sel.result(), [0])
        sel.set_filter("po")                                   # pomme + poire
        self.assertEqual(sel.visible, [0, 1])
        sel.select_visible(True)
        self.assertEqual(sel.result(), [0, 1])
        sel.invert_visible()
        self.assertEqual(sel.result(), [])
        sel.set_filter("jaune")                                # le filtre cherche aussi dans le détail
        self.assertEqual(sel.visible, [2])
        sel.set_filter("zzz")
        sel.toggle()                                           # liste vide : sans effet, sans erreur
        self.assertEqual(sel.result(), [])

    def test_cursor_bounds_and_filter_keeps_cursor(self):
        sel = s.Selector(list("abcde"))
        sel.move(99)
        self.assertEqual(sel.cur, 4)
        sel.move(-99)
        self.assertEqual(sel.cur, 0)
        sel.end()
        sel.set_filter("e")
        self.assertEqual(sel.visible[sel.cur], 4)              # l'élément courant reste visé

    def test_preselect_all_and_parse(self):
        sel = s.Selector(["a", "b", "c", "d", "e"], selected="all")
        self.assertEqual(len(sel.result()), 5)
        sel.parse("n")
        self.assertEqual(sel.result(), [])
        sel.parse("1,3-4")
        self.assertEqual(sel.result(), [0, 2, 3])
        sel.parse("/e")
        self.assertEqual(sel.result(), [0, 2, 3, 4])
        for bad in ("9", "0", "4-2", "x"):
            with self.assertRaises(ValueError):
                sel.parse(bad)

    def test_plain_ui(self):
        class Tty:
            def __init__(self, lines):
                self.lines, self.out = iter(lines), []

            def readline(self):
                return next(self.lines, "")

            def write(self, t):
                self.out.append(t)

            def flush(self):
                pass
        sel = s.Selector(["un", "deux", "trois"])
        tty = Tty(["x9\n", "2-3\n", "\n"])                    # saisie invalide, puis 2-3, puis validation
        self.assertEqual(s.plain_ui(sel, "titre", tty, tty), [1, 2])
        self.assertIn("saisie invalide", "".join(tty.out))
        self.assertIsNone(s.plain_ui(s.Selector(["a"]), "t", Tty(["q\n"]), Tty([])))   # annulation
        self.assertIsNone(s.plain_ui(s.Selector(["a"]), "t", Tty([]), Tty([])))        # EOF = annulation


class PickHelpers(unittest.TestCase):
    """pick_results / pick_entries / pick_links : la sélection filtre bien les données (interface simulée)."""

    def setUp(self):
        setup_args("-i")
        self.orig = s.run_selector

    def tearDown(self):
        s.run_selector = self.orig

    def test_pick_results(self):
        res = [{"title": f"t{i}", "url": f"https://x.org/{i}", "snippet": "", "engine": "e"} for i in range(3)]
        s.run_selector = lambda *a, **k: [0, 2]
        self.assertEqual([r["url"] for r in s.pick_results(res, "q")], ["https://x.org/0", "https://x.org/2"])
        s.run_selector = lambda *a, **k: []
        self.assertEqual(s.pick_results(res, "q"), [])

    def test_pick_entries_updates_count(self):
        tl = {"sources": [], "count": 3, "items": [{"line": l, "source": "u"} for l in "abc"]}
        s.run_selector = lambda *a, **k: [1]
        out = s.pick_entries(tl)
        self.assertEqual((out["count"], [i["line"] for i in out["items"]]), (1, ["b"]))

    def test_pick_links_builds_selection_page(self):
        pages = [{"url": "https://a.org", "links": [{"text": "x", "url": "https://a.org/1"}, {"text": "", "url": "https://a.org/2"}]}]
        s.run_selector = lambda *a, **k: [1]
        out = s.pick_links(pages)
        self.assertEqual(out[0]["links"], [{"text": "", "url": "https://a.org/2"}])

    def test_cancel_exits_130(self):
        s.run_selector = lambda *a, **k: None
        with self.assertRaises(SystemExit) as cm:
            s.pick_results([{"title": "t", "url": "https://x.org", "snippet": "", "engine": "e"}], "q")
        self.assertEqual(cm.exception.code, 130)


class Security(unittest.TestCase):
    """Portée des cookies, filtre du réseau privé, redirections, pause par hôte."""

    def setUp(self):
        self.srv = MiniServer({"/echo": ("text/plain", "{ECHO}"), "/hello": ("text/plain", "bonjour"),
                               "/redir_private": ("302", "{BASE}/echo"), "/redir_local": ("302", "/echo")})
        self.port = self.srv.srv.server_port
        self.loc = f"http://localhost:{self.port}"          # « localhost » et 127.0.0.1 = deux hôtes différents
        self.ip = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.srv.close()

    def fetch_body(self, url):
        return s.fetch(url, retries=0)[0]

    # -- filtre d'adresses
    def test_blocked_ip_table(self):
        setup_args()
        for bad in ("127.0.0.1", "10.1.2.3", "192.168.0.1", "172.16.5.5", "169.254.169.254", "100.64.0.9", "0.0.0.0",
                    "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "not-an-ip"):
            self.assertTrue(s.is_blocked_ip(bad), bad)
        for good in ("8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"):
            self.assertFalse(s.is_blocked_ip(good), good)

    def test_private_target_blocked_by_default(self):
        setup_args()
        s.ARGS.allow_private = False
        with self.assertRaises(Exception) as cm:
            self.fetch_body(self.loc + "/hello")
        self.assertIn("adresse privée bloquée", str(cm.exception))

    def test_trusted_host_and_allow_private(self):
        setup_args()
        s.ARGS.allow_private = False
        s.ARGS._trusted = {"localhost"}                      # comme un -u explicite
        self.assertEqual(self.fetch_body(self.loc + "/hello"), "bonjour")
        with self.assertRaises(Exception):
            self.fetch_body(self.ip + "/hello")               # 127.0.0.1 n'est pas de confiance
        s.ARGS.allow_private = True
        self.assertEqual(self.fetch_body(self.ip + "/hello"), "bonjour")

    def test_setup_security_trusts_explicit_targets_and_searx(self):
        setup_args("--allow-host", "Interne.lan", "--searx", "http://127.0.0.1:8888")
        s.ARGS.allow_private = False
        s.setup_security([self.loc + "/x", "pas-une-url"])
        self.assertEqual(s.ARGS._trusted, {"interne.lan", "localhost", "127.0.0.1"})

    def test_redirect_to_private_host_is_blocked(self):
        setup_args()
        s.ARGS.allow_private = False
        s.ARGS._trusted = {"localhost"}                      # l'origine est de confiance, pas la cible de la redirection
        s.ARGS.retries = 0
        with self.assertRaises(Exception) as cm:
            self.fetch_body(self.loc + "/redir_private")
        self.assertIn("adresse privée bloquée", str(cm.exception))

    def test_render_refuses_private_before_launching_browser(self):
        setup_args("--render")
        s.ARGS.allow_private = False
        with self.assertRaises(ValueError) as cm:
            s.render_dom("http://127.0.0.1:9/")
        self.assertIn("adresse privée", str(cm.exception))

    # -- cookies et en-têtes
    def test_cookie_only_sent_to_targeted_host(self):
        setup_args("--cookie", "sid=42", "-H", "X-Token: abc")
        s.setup_security([self.loc + "/echo"])
        self.assertEqual(s.ARGS._scope, {"localhost"})
        self.assertEqual(self.fetch_body(self.loc + "/echo"), "cookie=sid=42;token=abc")   # hôte ciblé
        self.assertEqual(self.fetch_body(self.ip + "/echo"), "cookie=;token=")             # autre hôte : rien

    def test_cookie_stripped_on_cross_host_redirect_kept_on_same_host(self):
        setup_args("--cookie", "sid=42", "-H", "X-Token: abc")
        s.setup_security([self.loc + "/x"])
        self.assertEqual(self.fetch_body(self.loc + "/redir_local"), "cookie=sid=42;token=abc")   # même hôte : conservé
        # redirection localhost -> 127.0.0.1 : cookie ET en-tête perso retirés
        srv2 = MiniServer({"/go": ("302", f"{self.ip}/echo")})
        try:
            self.assertEqual(self.fetch_body(f"http://localhost:{srv2.srv.server_port}/go"), "cookie=;token=")
        finally:
            srv2.close()

    def test_cookie_domain_overrides_targets(self):
        setup_args("--cookie", "sid=1", "--cookie-domain", "127.0.0.1")
        s.setup_security([self.loc + "/echo"])
        self.assertEqual(s.ARGS._scope, {"127.0.0.1"})
        self.assertEqual(self.fetch_body(self.loc + "/echo"), "cookie=;token=")
        self.assertEqual(self.fetch_body(self.ip + "/echo"), "cookie=sid=1;token=")

    def test_cookie_without_target_is_dropped_and_never_reaches_search_engine(self):
        mock = SearxMock()
        try:
            setup_args("--cookie", "sid=secret", "--searx", mock.url)
            s.ARGS.quiet = False
            err, old = io.StringIO(), sys.stderr
            sys.stderr = err
            try:
                s.setup_security([])                                                      # recherche seule, aucune cible
            finally:
                sys.stderr = old
            self.assertIn("ignorés", err.getvalue())
            self.assertEqual(s._host_match("localhost", s.ARGS._scope), False)
            s.eng_searxng("x", 1)
            self.assertIsNone(mock.seen_cookie)                                           # le moteur n'a jamais vu le cookie
        finally:
            mock.close()

    def test_plaintext_cookie_warning(self):
        setup_args("--cookie", "sid=1")
        s.ARGS.quiet = False
        err, old = io.StringIO(), sys.stderr
        sys.stderr = err
        try:
            s.setup_security(["http://exemple.org/"])
        finally:
            sys.stderr = old
        self.assertIn("en clair", err.getvalue())

    # -- politesse par hôte
    def test_throttle_spaces_requests_per_host(self):
        setup_args("--delay", "0.3")
        s._next_ok.clear()
        t0 = time.monotonic()
        for _ in range(3):
            self.fetch_body(self.ip + "/hello")
        self.assertGreaterEqual(time.monotonic() - t0, 0.55)                              # 2 pauses de 0,3 s

    def test_throttle_applies_across_threads_but_not_across_hosts(self):
        setup_args("--delay", "0.3")
        s._next_ok.clear()
        t0 = time.monotonic()
        threads = [threading.Thread(target=lambda: self.fetch_body(self.ip + "/hello")) for _ in range(4)]
        [th.start() for th in threads]
        [th.join() for th in threads]
        self.assertGreaterEqual(time.monotonic() - t0, 0.85)                              # 4 threads, un seul site : espacés
        s._next_ok.clear()
        t0 = time.monotonic()
        self.fetch_body(self.ip + "/hello")
        self.fetch_body(self.loc + "/hello")                                              # hôtes différents : pas d'attente
        self.assertLess(time.monotonic() - t0, 0.25)


class MiniProxy:
    """Proxy HTTP minimal : note la ligne de requête (URL absolue) et relaie tout vers un serveur local fixe."""

    def __init__(self, backend_port):
        seen = self.seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(inner):
                seen.append(inner.path)
                import http.client as hc
                c = hc.HTTPConnection("127.0.0.1", backend_port, timeout=5)
                c.request("GET", "/" + inner.path.split("/", 3)[-1])
                r = c.getresponse()
                body = r.read()
                inner.send_response(r.status)
                inner.send_header("Content-Type", r.getheader("Content-Type", "text/plain"))
                inner.end_headers()
                inner.wfile.write(body)
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class ProxySupport(unittest.TestCase):
    def setUp(self):
        self.backend = MiniServer({"/hello": ("text/plain", "bonjour via proxy")})
        self.port = self.backend.srv.server_port
        self.proxy = MiniProxy(self.port)

    def tearDown(self):
        self.proxy.close()
        self.backend.close()
        s._direct = None

    def test_remote_host_goes_through_proxy(self):
        setup_args("--proxy", self.proxy.url)
        s._opener = s.build_opener(s.ARGS.proxy)
        body, _, _ = s.fetch(f"http://example.test:{self.port}/hello", retries=0)      # nom non résolvable : seul le proxy peut répondre
        self.assertEqual(body, "bonjour via proxy")
        self.assertEqual(self.proxy.seen, [f"http://example.test:{self.port}/hello"])

    def test_local_hosts_bypass_the_proxy(self):
        setup_args("--proxy", "http://127.0.0.1:1")                                    # proxy mort : un détour ferait échouer
        s._opener = s.build_opener(s.ARGS.proxy)
        s._direct = None
        for host in ("127.0.0.1", "localhost"):
            body, _, _ = s.fetch(f"http://{host}:{self.port}/hello", retries=0)
            self.assertEqual(body, "bonjour via proxy")
        self.assertEqual(self.proxy.seen, [])

    def test_is_local_host(self):
        for h in ("localhost", "127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "a.localhost"):
            self.assertTrue(s.is_local_host(h), h)
        for h in ("example.com", "8.8.8.8", "www.raspberrypi.com"):
            self.assertFalse(s.is_local_host(h), h)

    def test_dead_proxy_error_names_the_proxy(self):
        setup_args("--proxy", "http://127.0.0.1:1")
        s._opener = s.build_opener(s.ARGS.proxy)
        with self.assertRaises(urllib.error.URLError) as cm:
            s.fetch("http://example.test/", retries=0)
        self.assertIn("--proxy", str(cm.exception))
        self.assertIn("127.0.0.1:1", str(cm.exception))


class SearxMock:
    """Faux SearXNG : renvoie 3 résultats fixes pour toute requête."""

    def __init__(self):
        body = json.dumps({"results": [
            {"title": "Premier", "url": "https://ex.org/1", "content": "c1", "engines": ["x"]},
            {"title": "Deuxième", "url": "https://ex.org/2", "content": "c2", "engines": ["x"]},
            {"title": "Troisième", "url": "https://ex.org/3", "content": "c3", "engines": ["x"]}]}).encode()

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(inner):
                self_.seen_cookie = inner.headers.get("Cookie")
                inner.send_response(200)
                inner.send_header("Content-Type", "application/json")
                inner.end_headers()
                inner.wfile.write(body)
        self_ = self
        self.seen_cookie = None
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def run_in_pty(argv, keys, out_path, timeout=25, marker="cochés"):
    """Lance scrapaud dans un vrai pseudo-terminal, envoie des touches, stdout redirigé vers un fichier."""
    import fcntl
    import pty
    import select
    import termios
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrapaud.py")
    pid, fd = pty.fork()
    if pid == 0:
        out = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        os.dup2(out, 1)
        os.execvpe(sys.executable, [sys.executable, script, *argv], dict(os.environ, TERM="xterm"))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    buf, sent, status = b"", False, None
    deadline = time.time() + timeout
    while time.time() < deadline:
        if select.select([fd], [], [], 0.2)[0]:
            try:
                buf += os.read(fd, 65536)
            except OSError:
                pass
        if not sent and marker.encode() in buf:
            time.sleep(0.3)
            for k in keys:
                os.write(fd, k.encode())
                time.sleep(0.15)
            sent = True
        done, st = os.waitpid(pid, os.WNOHANG)
        if done:
            status = os.waitstatus_to_exitcode(st)
            break
    else:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        status = "TIMEOUT"
    with open(out_path, encoding="utf-8") as f:
        return status, f.read().split("\n")


@unittest.skipUnless(sys.platform.startswith("linux") and s.curses is not None, "pty/curses requis")
class InteractiveEndToEnd(unittest.TestCase):
    """L'interface curses réelle, pilotée touche par touche ; le résultat sort sur stdout (pipeable)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.list = os.path.join(self.tmp, "l.txt")
        with open(self.list, "w") as f:
            f.write("alpha\nbruit1\nbeta\nbruit2\ngamma\n")
        self.out = os.path.join(self.tmp, "out.txt")

    def test_textlist_uncheck_noise(self):
        st, out = run_in_pty(["--textlist", "-u", self.list, "-i", "--quiet"], ["j", " ", "j", " ", "\r"], self.out)
        self.assertEqual(st, 0)
        self.assertEqual([l for l in out if l], ["alpha", "beta", "gamma"])

    def test_filter_then_select_visible(self):
        keys = ["n", "/", "b", "e", "t", "\r", "a", "\r"]     # rien, filtre « bet », tout cocher (visible), valider
        st, out = run_in_pty(["--textlist", "-u", self.list, "-i", "--quiet"], keys, self.out)
        self.assertEqual((st, [l for l in out if l]), (0, ["beta"]))

    def test_cancel_returns_130_and_prints_nothing(self):
        st, out = run_in_pty(["--textlist", "-u", self.list, "-i", "--quiet"], ["q"], self.out)
        self.assertEqual(st, 130)
        self.assertEqual([l for l in out if l], [])

    def test_plain_mode_over_a_real_tty(self):
        st, out = run_in_pty(["--textlist", "-u", self.list, "-i", "--plain", "--quiet"],
                             ["1,3,5\n", "\n"], self.out, marker="Sélection")
        self.assertEqual((st, [l for l in out if l]), (0, ["alpha", "beta", "gamma"]))

    def test_search_results_selection(self):
        mock = SearxMock()
        try:
            argv = ["-q", "x", "--searx", mock.url, "-e", "searxng", "-i", "--urls-only", "--no-cache", "--quiet"]
            st, out = run_in_pty(argv, [" ", "j", " ", "\r"], self.out)      # coche 1er, saute le 2e, coche le 3e
        finally:
            mock.close()
        self.assertEqual(st, 0)
        self.assertEqual([l for l in out if l], ["https://ex.org/1", "https://ex.org/3"])


class Wordlists(unittest.TestCase):
    def setUp(self):
        setup_args("--wordlist")
        self.tmp = tempfile.mkdtemp()

    def test_tokenize_options(self):
        text = "Le pare-feu détecte l'intrusion en 2026 : cybersécurité, IA!"
        self.assertEqual(s.tokenize(text)[:4], ["pare", "feu", "détecte", "intrusion"])          # min 3, sans chiffres
        s.ARGS.wl_hyphen = True
        self.assertIn("pare-feu", s.tokenize(text))
        s.ARGS.wl_digits, s.ARGS.wl_lower = True, True
        self.assertIn("2026", s.tokenize(text))
        self.assertIn("cybersécurité", s.tokenize(text))
        s.ARGS.wl_min = 2
        self.assertIn("ia", s.tokenize(text))
        s.ARGS._wl_stop = s.STOPWORDS["fr"]
        self.assertNotIn("le", s.tokenize(text))

    def test_list_like_and_mode_auto(self):
        lst = ["admin", "backup", "dev", "staging", "www", "mail"]
        prose = ["Ceci est une longue phrase qui ne ressemble pas à une liste de mots."] * 6
        self.assertTrue(s.list_like(lst))
        self.assertFalse(s.list_like(prose))
        self.assertEqual(s.wl_entries("plain", lst + ["# c"]), lst + ["# c"])           # mode lignes : tel quel
        s.ARGS.strip_comments = True
        self.assertEqual(s.wl_entries("plain", lst + ["# c"]), lst)
        self.assertIn("phrase", s.wl_entries("plain", prose))                           # prose -> mots
        self.assertEqual(s.wl_entries("text", ["admin", "backup"] * 3)[:2], ["admin", "backup"])  # HTML -> mots

    def test_agg_sort_and_limits(self):
        agg = s.WordAgg(keep_sources=True)
        agg.add(["b", "a", "b", "c", "b", "a"], "src1")
        agg.add(["c"], "src2")
        self.assertEqual((agg.unique, agg.total), (3, 7))
        self.assertEqual(list(agg.recent), ["b", "a", "c"])                            # nouveautés seulement
        self.assertEqual(s.wl_sorted(agg.counter), [("b", 3), ("a", 2), ("c", 2)])     # fréquence puis alpha
        s.ARGS.wl_sort = "alpha"
        self.assertEqual([w for w, _ in s.wl_sorted(agg.counter)], ["a", "b", "c"])
        s.ARGS.wl_sort, s.ARGS.wl_min_count = "none", 3
        self.assertEqual(s.wl_sorted(agg.counter), [("b", 3)])
        self.assertEqual(sorted(agg.per_source), ["src1", "src2"])

    def test_slugify(self):
        self.assertEqual(s.slugify("https://www.Exemple.com/Mes Mots?x=1"), "exemple-com-mes-mots-x-1")
        self.assertEqual(s.slugify("???"), "wordlist")
        self.assertLessEqual(len(s.slugify("a" * 200)), 40)

    def test_write_files_manifest_split(self):
        s.ARGS.wl_dir, s.ARGS.wl_split = os.path.join(self.tmp, "out"), True
        agg = s.WordAgg(keep_sources=True)
        agg.add(["alpha", "beta", "alpha"], "http://a.org/x")
        agg.add(["gamma"], "http://b.org/y")
        items = s.wl_sorted(agg.counter)
        report = [{"url": u, "kind": "text", "entries": 1, "error": None} for u in agg.per_source]
        files = s.wl_write(items, agg, report, "sujet")
        names = [os.path.basename(f) for f in files]
        self.assertEqual(names[0], "wordlist.txt")
        self.assertEqual(sum(n.endswith(".txt") for n in names), 3)                    # merged + 2 sources
        with open(files[0]) as f:
            self.assertEqual(f.read().split(), ["alpha", "beta", "gamma"])
        with open(files[-1]) as f:
            m = json.load(f)
        self.assertEqual((m["uniques"], m["vus"], m["sujet"]), (3, 4, "sujet"))

    def test_output_flag_writes_single_file_no_dir(self):
        s.ARGS.output = os.path.join(self.tmp, "sub", "mots.txt")
        agg = s.WordAgg()
        agg.add(["un", "deux"], "u")
        files = s.wl_write(s.wl_sorted(agg.counter), agg, [], "x")
        self.assertEqual(files, [s.ARGS.output])
        self.assertEqual(os.listdir(os.path.join(self.tmp, "sub")), ["mots.txt"])

    def test_disk_guard_refuses(self):
        s.ARGS.wl_dir = os.path.join(self.tmp, "full")
        orig = s.free_space
        s.free_space = lambda p: 1024                                                  # disque « plein »
        try:
            with self.assertRaises(SystemExit) as cm:
                s.wl_write([("mot", 1)], s.WordAgg(), [], "x")
            self.assertIn("espace disque", str(cm.exception))
            self.assertFalse(os.path.exists(s.ARGS.wl_dir))                            # rien n'a été créé
        finally:
            s.free_space = orig

    def test_crawl_same_domain_depth_and_scripts(self):
        pages = {"/i.html": ("text/html", '<p>racine unique</p><a href="/p.html">p</a><a href="http://autre.invalid/x">e</a>'),
                 "/p.html": ("text/html", "<p>profondeur seconde</p><script>var caché=1;</script>")}
        srv = MiniServer(pages)
        try:
            s.ARGS.depth = 1
            agg = s.WordAgg()
            live = s.LiveView("t", agg)
            report = s.wl_crawl([srv.url + "/i.html"], agg, live)
            words = set(agg.counter)
            self.assertEqual(len(report), 2)                                            # l'externe n'est pas suivi
            self.assertTrue({"racine", "unique", "profondeur", "seconde"} <= words)
            self.assertNotIn("caché", words)                                            # <script> ignoré
            s.ARGS.depth = 0
            agg2 = s.WordAgg()
            self.assertEqual(len(s.wl_crawl([srv.url + "/i.html"], agg2, live)), 1)
        finally:
            srv.close()

    def test_interactive_pruning_before_writing(self):
        srv = MiniServer({"/i.html": ("text/html", "<p>alpha alpha beta gamma</p>")})
        orig = s.run_selector
        try:
            s.ARGS.interactive, s.ARGS.quiet = True, True
            s.ARGS.wl_dir = os.path.join(self.tmp, "sel")
            seen = {}
            def fake(labels, details, selected, title, **k):
                seen["labels"], seen["selected"] = labels, selected
                return [0, 2]                                                           # garde « alpha » et « gamma »
            s.run_selector = fake
            self.assertEqual(s.run_wordlist([srv.url + "/i.html"], "t"), 0)
            with open(os.path.join(s.ARGS.wl_dir, "wordlist.txt")) as f:
                self.assertEqual(f.read().split(), ["alpha", "gamma"])
            self.assertEqual(seen["selected"], "all")                                   # tout coché au départ
            self.assertEqual(seen["labels"][0], "alpha  ×2")                            # fréquence visible
        finally:
            s.run_selector = orig
            srv.close()

    def test_error_source_is_reported_not_fatal(self):
        srv = MiniServer({})
        try:
            agg = s.WordAgg()
            rep = s.wl_page(srv.url + "/absent.html", agg, s.LiveView("t", agg))
            self.assertIn("404", rep["error"])
        finally:
            srv.close()

    def test_live_frame_content(self):
        agg = s.WordAgg()
        agg.add(["alpha", "beta", "alpha"], "u")
        live = s.LiveView("wordlist en direct", agg, total=3)
        live.src("https://a.org/x", "run")
        live.src("https://b.org/y", "ok", 1234)
        live.src("https://c.org/z", "err")
        live.log("\033[92mmessage\033[0m")
        text = "\n".join(l for l, _ in live.frame(100, 30))
        for expected in ("wordlist en direct", "sources 2/3", "uniques 2", "vus 3", "a.org/x", "lecture", "1 234", "erreur",
                         "alpha", "top", "×2", "message"):
            self.assertIn(expected, text)
        self.assertNotIn("\033", text)                                                  # aucune séquence ANSI dans le texte
        self.assertFalse(live.enabled)                                                  # pas de tty ici

    def test_live_frame_respects_small_terminal(self):
        agg = s.WordAgg()
        agg.add([f"mot{i}" for i in range(500)], "u")
        live = s.LiveView("t", agg, total=50)
        for i in range(50):
            live.src(f"https://site{i}.org/page", "ok", i)
        frame = live.frame(60, 12)
        self.assertLessEqual(len(frame), 10)                                            # tient dans la hauteur


def run_pty_capture(argv, timeout=40):
    """Lance scrapaud dans un pty : renvoie (code, sortie brute du terminal, lignes de stdout redirigé)."""
    import fcntl
    import pty
    import select
    import termios
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrapaud.py")
    out_path = tempfile.mktemp()
    pid, fd = pty.fork()
    if pid == 0:
        out = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        os.dup2(out, 1)
        os.execvpe(sys.executable, [sys.executable, script, *argv], dict(os.environ, TERM="xterm"))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
    buf, status = b"", None
    deadline = time.time() + timeout
    while time.time() < deadline:
        if select.select([fd], [], [], 0.1)[0]:
            try:
                buf += os.read(fd, 65536)
            except OSError:
                pass
        done, st = os.waitpid(pid, os.WNOHANG)
        if done:
            status = os.waitstatus_to_exitcode(st)
            break
    else:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        status = "TIMEOUT"
    with open(out_path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    os.unlink(out_path)
    return status, buf.decode("utf-8", "replace"), lines


class WordlistEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.srv = MiniServer({"/i.html": ("text/html", "<p>cybersécurité cybersécurité souveraineté</p>"),
                               "/l.txt": ("text/plain", "admin\nbackup\ndev\nstaging\nwww\nmail\n")})

    def tearDown(self):
        self.srv.close()

    def test_cli_words_and_lines_sources(self):
        out = os.path.join(self.tmp, "w")
        r = os_run([sys.executable, SCRIPT, "--wordlist", "-u", self.srv.url + "/i.html", "-u", self.srv.url + "/l.txt",
                    "--wl-dir", out, "--quiet"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split("\n")[0], os.path.join(out, "wordlist.txt"))    # chemins sur stdout (pipeable)
        with open(os.path.join(out, "wordlist.txt")) as f:
            words = f.read().split()
        self.assertEqual(words[0], "cybersécurité")                                     # vue 2 fois : en tête (tri par fréquence)
        self.assertEqual(words[1:], sorted(words[1:]))                                  # ex æquo : ordre alphabétique
        self.assertTrue({"souveraineté", "admin", "backup", "mail"} <= set(words))      # fichier-liste gardé tel quel

    def test_cli_live_view_in_pty(self):
        out = os.path.join(self.tmp, "live")
        st, raw, lines = run_pty_capture(["--wordlist", "-u", self.srv.url + "/i.html", "-u", self.srv.url + "/l.txt",
                                          "--wl-dir", out, "--delay", "0.4"])
        self.assertEqual(st, 0)
        self.assertIn("\x1b[?25l", raw)                                                 # curseur masqué pendant le live
        self.assertTrue(raw.rstrip().rfind("\x1b[?25h") != -1)                          # ... puis restauré
        plain = __import__("re").sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\r", "", raw)
        for expected in ("wordlist en direct", "sources 2/2", "uniques", "cybersécurité"):
            self.assertIn(expected, plain)
        self.assertEqual(lines[0], os.path.join(out, "wordlist.txt"))
        self.assertTrue(os.path.exists(os.path.join(out, "manifest.json")))

    def test_cli_no_live_flag_and_quiet(self):
        st, raw, _ = run_pty_capture(["--wordlist", "-u", self.srv.url + "/l.txt", "--wl-dir", os.path.join(self.tmp, "n"),
                                      "--no-live"])
        self.assertEqual(st, 0)
        self.assertNotIn("\x1b[?25l", raw)                                              # aucun tableau de bord
        self.assertIn("entrées uniques", raw)

    def test_textlist_also_gets_live_view(self):
        st, raw, lines = run_pty_capture(["--textlist", "-u", self.srv.url + "/l.txt", "--delay", "0.3"])
        self.assertEqual(st, 0)
        self.assertIn("liste en direct", __import__("re").sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\r", "", raw))
        self.assertEqual([l for l in lines if l][:2], ["admin", "backup"])              # la liste reste sur stdout, sans live


PAGE_WITH_CHROME = """<html class="vector-feature-language-in-header"><head><title>Titre</title></head>
<body class="skin-vector vector-toc-pinned has-sidebar">
<header class="site-header"><a href="/">Accueil</a><a href="/a-propos">À propos</a></header>
<nav class="main-menu"><ul><li><a href="/x">Menu un</a></li><li><a href="/y">Menu deux</a></li></ul></nav>
<div id="cookie-banner"><p>Nous utilisons des cookies. Accepter tout</p></div>
<div class="site-content has-sidebar"><aside class="sidebar"><ul><li>Widget récent</li></ul></aside>
<article class="post entry-content">
<h1>Cryptographie moderne</h1>
<p>La cryptographie protège les échanges grâce au <a href="/chiffrement">chiffrement</a> des messages sensibles et à l'authentification rigoureuse des correspondants.</p>
<p>Les algorithmes symétriques et asymétriques se complètent dans les protocoles actuels de communication sécurisée.</p>
<p>Les algorithmes symétriques et asymétriques se complètent dans les protocoles actuels de communication sécurisée.</p>
<aside class="related-posts"><a href="/r1">Article lié un</a></aside>
<ul><li>clé publique</li><li>clé privée</li></ul>
</article></div>
<footer><p>© 2026 Tous droits réservés</p><a href="/mentions">Mentions légales</a></footer>
</body></html>"""


class MainContent(unittest.TestCase):
    def setUp(self):
        setup_args()

    def parse(self, html):
        p = s.PageParser("https://ex.org/")
        p.feed(html)
        return p

    def test_keeps_article_drops_chrome(self):
        text = " ".join(self.parse(PAGE_WITH_CHROME).main_pieces())
        for kept in ("Cryptographie moderne", "protège les échanges", "chiffrement", "symétriques", "clé publique"):
            self.assertIn(kept, text)                                 # y compris le texte du lien DANS un paragraphe
        for dropped in ("Accueil", "À propos", "Menu un", "cookies", "Widget récent", "Article lié", "Tous droits", "Mentions légales"):
            self.assertNotIn(dropped, text)

    def test_body_layout_classes_do_not_hide_content(self):
        # classes « vector-toc-pinned » / « has-sidebar » sur <body> et un conteneur : ne doivent pas tout classer en interface
        self.assertGreater(len(self.parse(PAGE_WITH_CHROME).main_pieces()), 3)

    def test_ui_inside_article_stays_ui_and_article_inside_sidebar_wrapper_stays_content(self):
        p = self.parse(PAGE_WITH_CHROME)
        links = [l["url"] for l in p.links_main]
        self.assertIn("https://ex.org/chiffrement", links)            # lien du texte
        self.assertNotIn("https://ex.org/r1", links)                  # <aside> dans l'article = interface
        self.assertNotIn("https://ex.org/x", links)                   # menu
        self.assertEqual(p.items_main, ["clé publique", "clé privée"])   # items du menu / widget exclus

    def test_consecutive_duplicates_removed(self):
        pieces = self.parse(PAGE_WITH_CHROME).main_pieces()
        self.assertEqual(sum("symétriques et asymétriques" in x for x in pieces), 1)

    def test_fallback_without_article(self):
        html = "<body><nav>Menu</nav><div><p>Un contenu simple sans balise article mais avec du vrai texte.</p></div><footer>pied</footer></body>"
        self.assertEqual(self.parse(html).main_pieces(), ["Un contenu simple sans balise article mais avec du vrai texte."])

    def test_short_link_text_outside_paragraph_dropped(self):
        html = "<body><div><a href='/1'>Lien court</a><p>Paragraphe suffisamment long pour rester dans le contenu principal.</p></div></body>"
        self.assertEqual(len(self.parse(html).main_pieces()), 1)

    def test_boilerplate_text_dropped_even_outside_ui_containers(self):
        html = ("<body><div><p>Nous utilisons des cookies. Accepter</p><p>Partager cet article</p>"
                "<p>Ce paragraphe long parle des cookies de navigation web et de leur fonctionnement technique détaillé dans les navigateurs.</p>"
                "<p>Contenu utile</p></div></body>")
        pieces = self.parse(html).main_pieces()
        self.assertEqual(pieces[0].startswith("Ce paragraphe long"), True)            # court + boilerplate : retirés ; long : gardé
        self.assertIn("Contenu utile", pieces)
        self.assertEqual(len(pieces), 2)

    def test_body_layout_classes_without_main_element(self):
        # sans <main>/<article>, seule la règle « html/body ne comptent pas » évite de tout classer en interface
        html = '<html class="has-sidebar"><body class="vector-toc-pinned"><div><p>Un texte réel qui doit être conservé malgré les classes de mise en page.</p></div></body></html>'
        self.assertEqual(len(self.parse(html).main_pieces()), 1)

    def test_default_resolution_of_main_flag(self):
        self.assertTrue(s.parse_args(["--wordlist", "-q", "x", "--no-searx"])[0].main)
        self.assertFalse(s.parse_args(["--wordlist", "--no-main", "-q", "x", "--no-searx"])[0].main)
        self.assertFalse(s.parse_args(["--textlist", "-q", "x", "--no-searx"])[0].main)
        self.assertTrue(s.parse_args(["--main", "-q", "x", "--no-searx"])[0].main)

    def test_scrape_page_and_wordlist_use_main(self):
        srv = MiniServer({"/p.html": ("text/html", PAGE_WITH_CHROME)})
        try:
            s.ARGS.main, s.ARGS._extract = True, {"text", "links", "items"}
            pg = s.scrape_page(srv.url + "/p.html")
            self.assertIn("cryptographie", pg["text"].lower())
            self.assertNotIn("Menu un", pg["text"])
            self.assertEqual([l["url"].rsplit("/", 1)[-1] for l in pg["links"]], ["chiffrement"])
            s.ARGS.main = False                                       # sans --main : tout le texte, menus compris
            self.assertIn("Menu un", s.scrape_page(srv.url + "/p.html")["text"])
            s.ARGS.main, s.ARGS.wl_lower = True, True
            words = set(s.wl_entries(*s.wl_fetch(srv.url + "/p.html")[:2]))
            self.assertIn("cryptographie", words)
            self.assertNotIn("widget", words)
            self.assertNotIn("cookies", words)
        finally:
            srv.close()


class Doctor(unittest.TestCase):
    def setUp(self):
        setup_args()
        self.tmp = tempfile.mkdtemp()
        self.orig = (s.shutil.which, s.shutil.disk_usage, s.find_browser)

    def tearDown(self):
        s.shutil.which, s.shutil.disk_usage, s.find_browser = self.orig

    def by_name(self, checks, name):
        return next(c for c in checks if c[1] == name)

    def test_optional_tools_reported_as_warnings(self):
        s.shutil.which = lambda n: None
        s.find_browser = lambda: (_ for _ in ()).throw(ValueError("aucun"))
        checks = s.doctor_local()
        self.assertEqual(self.by_name(checks, "Lecture PDF (pdftotext)")[0], s.WARN)
        self.assertEqual(self.by_name(checks, "Rendu JavaScript (--render)")[0], s.WARN)

    def test_disk_thresholds(self):
        import collections
        DU = collections.namedtuple("DU", "total used free")
        for free_gb, expected in ((100, s.OK), (4.6, s.WARN), (0.2, s.ERR)):
            s.shutil.disk_usage = lambda p, f=free_gb: DU(500 * 2**30, 0, int(f * 2**30))
            self.assertEqual(self.by_name(s.doctor_local(), "Disque (home)")[0], expected, free_gb)
        s.shutil.disk_usage = lambda p: DU(100 * 2**30, 0, 20 * 2**30)          # 80 % utilisé, 20 Go libres
        self.assertEqual(self.by_name(s.doctor_local(), "Disque (home)")[0], s.OK)
        s.shutil.disk_usage = lambda p: DU(1000 * 2**30, 0, 40 * 2**30)         # 96 % utilisé
        self.assertEqual(self.by_name(s.doctor_local(), "Disque (home)")[0], s.WARN)

    def test_config_states(self):
        cfg = os.path.join(self.tmp, "c.toml")
        s.ARGS.config = cfg
        self.assertEqual(self.by_name(s.doctor_local(), "Configuration")[0], s.NOTE)      # absent
        with open(cfg, "w") as f:
            f.write('limit = 5\nnot-domain = ["a.com"]\n')
        self.assertEqual(self.by_name(s.doctor_local(), "Configuration")[0], s.OK)
        with open(cfg, "w") as f:
            f.write('limit = 5\nbogus = 1\n')
        st, _, detail = self.by_name(s.doctor_local(), "Configuration")
        self.assertEqual(st, s.WARN)
        self.assertIn("bogus", detail)
        with open(cfg, "w") as f:
            f.write("ceci = = pas du toml")
        self.assertEqual(self.by_name(s.doctor_local(), "Configuration")[0], s.ERR)

    def test_tor_port_and_searx(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        s.ARGS.tor_proxy = f"127.0.0.1:{listener.getsockname()[1]}"
        self.assertEqual(self.by_name(s.doctor_local(), "Tor (SOCKS5)")[0], s.OK)
        listener.close()
        self.assertEqual(self.by_name(s.doctor_local(), "Tor (SOCKS5)")[0], s.WARN)       # fermé = avertissement, pas erreur
        srv = MiniServer({"/healthz": ("text/plain", "OK")})
        try:
            s.ARGS.searx = srv.url
            self.assertEqual(self.by_name(s.doctor_local(), "SearXNG")[0], s.OK)
        finally:
            srv.close()
        self.assertEqual(self.by_name(s.doctor_local(), "SearXNG")[0], s.ERR)              # configuré mais injoignable
        s.ARGS.searx = None
        self.assertEqual(self.by_name(s.doctor_local(), "SearXNG")[0], s.WARN)             # non configuré

    def test_probe_engines_statuses_and_slow_engine_cap(self):
        orig = dict(s.ENGINES)
        try:
            s.ENGINES.clear()
            s.ENGINES.update(bon=lambda q, p: [{"url": "u"}], vide=lambda q, p: [],
                             bloque=lambda q, p: (_ for _ in ()).throw(urllib.error.HTTPError("u", 429, "x", {}, None)),
                             casse=lambda q, p: (_ for _ in ()).throw(RuntimeError("boum")),
                             lent=lambda q, p: time.sleep(5) or [{"url": "u"}])
            t0 = time.time()
            res = {n: (st, d) for st, n, d in s.probe_engines(limit=0.5)}
            self.assertLess(time.time() - t0, 2.5)                                          # n'attend pas le moteur lent
            self.assertEqual(res["Moteur bon"][0], s.OK)
            self.assertEqual(res["Moteur vide"][0], s.WARN)
            self.assertIn("429", res["Moteur bloque"][1])
            self.assertIn("boum", res["Moteur casse"][1])
            self.assertIn("pas de réponse", res["Moteur lent"][1])
        finally:
            s.ENGINES.clear()
            s.ENGINES.update(orig)

    def test_exit_code_and_json(self):
        orig = s.doctor_local
        try:
            s.doctor_local = lambda: [(s.OK, "a", "x"), (s.WARN, "b", "y")]
            self.assertEqual(s.run_doctor(), 0)                                             # avertissements : code 0
            s.doctor_local = lambda: [(s.OK, "a", "x"), (s.ERR, "b", "y")]
            self.assertEqual(s.run_doctor(), 1)                                             # erreur : code 1
        finally:
            s.doctor_local = orig

    def test_cli_doctor_json(self):
        r = os_run([sys.executable, SCRIPT, "--doctor", "--json", "--no-searx"])
        self.assertIn(r.returncode, (0, 1), r.stderr)
        names = [c["nom"] for c in json.loads(r.stdout)]
        for expected in ("Python", "Disque (home)", "Cache", "Filtre réseau privé"):
            self.assertIn(expected, names)


# ------------------------------------------------------------------ rendu réel de l'interface
import re as _re


class Screen:
    def __init__(self, rows=24, cols=100):
        self.rows, self.cols = rows, cols
        self.grid = [[(" ", frozenset()) for _ in range(cols)] for _ in range(rows)]
        self.r = self.c = 0
        self.attr = set()
        self.top, self.bot = 0, rows - 1
        self.last = " "
        self.saved = (0, 0)

    def _blank(self):
        return [(" ", frozenset())] * self.cols

    def _scroll_up(self, n=1):
        for _ in range(n):
            del self.grid[self.top]
            self.grid.insert(self.bot, list(self._blank()))

    def _scroll_down(self, n=1):
        for _ in range(n):
            del self.grid[self.bot]
            self.grid.insert(self.top, list(self._blank()))

    def _put(self, ch):
        if self.c >= self.cols:
            self.c = 0; self.r = min(self.r + 1, self.rows - 1)
        self.grid[self.r][self.c] = (ch, frozenset(self.attr)); self.c += 1; self.last = ch

    def _sgr(self, params):
        ps = [int(x) if x else 0 for x in (params.split(";") if params else ["0"])]
        for p in ps:
            if p == 0: self.attr = set()
            elif p == 1: self.attr.add("bold")
            elif p == 2: self.attr.add("dim")
            elif p == 7: self.attr.add("reverse")
            elif p in (27,): self.attr.discard("reverse")
            elif p in (22,): self.attr -= {"bold", "dim"}
            elif p in (32, 92): self.attr.add("green")
            elif p in (39,): self.attr.discard("green")

    def feed(self, data):
        i, n = 0, len(data)
        while i < n:
            ch = data[i]
            if ch == "\x1b":
                m = re.match(r"\x1b\[([?0-9;]*)([@-~])", data[i:])
                if m:
                    p, cmd = m.group(1), m.group(2); i += m.end()
                    num = lambda d=1: int(p.split(";")[0]) if p and p.split(";")[0].isdigit() else d
                    if cmd in "Hf":
                        a = p.split(";") if p else []
                        self.r = min(max((int(a[0]) if a and a[0] else 1) - 1, 0), self.rows - 1)
                        self.c = min(max((int(a[1]) if len(a) > 1 and a[1] else 1) - 1, 0), self.cols - 1)
                    elif cmd == "A": self.r = max(0, self.r - num())
                    elif cmd == "B": self.r = min(self.rows - 1, self.r + num())
                    elif cmd == "C": self.c = min(self.cols - 1, self.c + num())
                    elif cmd == "D": self.c = max(0, self.c - num())
                    elif cmd == "G": self.c = min(max(num() - 1, 0), self.cols - 1)
                    elif cmd == "d": self.r = min(max(num() - 1, 0), self.rows - 1)
                    elif cmd == "J":
                        mode = int(p) if p.isdigit() else 0
                        if mode == 2: self.grid = [[(" ", frozenset()) for _ in range(self.cols)] for _ in range(self.rows)]
                        elif mode == 0:
                            for c in range(self.c, self.cols): self.grid[self.r][c] = (" ", frozenset())
                            for r in range(self.r + 1, self.rows): self.grid[r] = [(" ", frozenset())] * self.cols
                    elif cmd == "K":
                        mode = int(p) if p.isdigit() else 0
                        rng = range(self.c, self.cols) if mode == 0 else (range(0, self.c + 1) if mode == 1 else range(self.cols))
                        for c in rng: self.grid[self.r][c] = (" ", frozenset())
                    elif cmd == "X":
                        for c in range(self.c, min(self.cols, self.c + num())): self.grid[self.r][c] = (" ", frozenset())
                    elif cmd == "m": self._sgr(p)
                    elif cmd == "P":
                        k = num(); row = self.grid[self.r]; row[self.c:self.c + k] = []; row.extend([(" ", frozenset())] * (self.cols - len(row)))
                    elif cmd == "@":
                        k = num(); row = self.grid[self.r]; row[self.c:self.c] = [(" ", frozenset())] * k; del row[self.cols:]
                    elif cmd == "L":
                        if self.top <= self.r <= self.bot:
                            for _ in range(num()):
                                del self.grid[self.bot]; self.grid.insert(self.r, list(self._blank()))
                    elif cmd == "M":
                        if self.top <= self.r <= self.bot:
                            for _ in range(num()):
                                del self.grid[self.r]; self.grid.insert(self.bot, list(self._blank()))
                    elif cmd == "S": self._scroll_up(num())
                    elif cmd == "T": self._scroll_down(num())
                    elif cmd == "b":
                        for _ in range(num()): self._put(self.last)
                    elif cmd == "r":
                        a = p.split(";") if p else []
                        self.top = (int(a[0]) - 1) if a and a[0] else 0
                        self.bot = (int(a[1]) - 1) if len(a) > 1 and a[1] else self.rows - 1
                        self.r = self.c = 0
                    elif cmd == "s": self.saved = (self.r, self.c)
                    elif cmd == "u": self.r, self.c = self.saved
                    continue
                if data[i:i + 2] == "\x1bM":
                    if self.r == self.top: self._scroll_down(1)
                    else: self.r -= 1
                    i += 2; continue
                if data[i:i + 2] == "\x1b7": self.saved = (self.r, self.c); i += 2; continue
                if data[i:i + 2] == "\x1b8": self.r, self.c = self.saved; i += 2; continue
                m = re.match(r"\x1b[()][0-9A-Za-z]|\x1b[=>78]|\x1b\][^\x07]*\x07", data[i:])
                i += m.end() if m else 1
                continue
            if ch == "\r": self.c = 0
            elif ch == "\n":
                if self.r == self.bot: self._scroll_up(1)
                else: self.r = min(self.r + 1, self.rows - 1)
            elif ch == "\b": self.c = max(0, self.c - 1)
            elif ch >= " ": self._put(ch)
            i += 1

    def lines(self):
        return ["".join(c for c, _ in row).rstrip() for row in self.grid]

    def render(self, mark=True):
        out = []
        for row in self.grid:
            text = "".join(c for c, _ in row).rstrip()
            flags = set().union(*(a for _, a in row))
            tag = ("▶" if "reverse" in flags else " ") if mark else ""
            out.append(f"{tag}│{text}")
        return "\n".join(out)


def screens_after(argv, keys, rows=14, cols=100, timeout=25):
    """Lance `scrapaud -i` dans un pty, rejoue la sortie dans l'émulateur et renvoie l'écran après chaque touche."""
    import fcntl
    import pty
    import select
    import termios
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrapaud.py")
    pid, fd = pty.fork()
    if pid == 0:
        os.dup2(os.open("/dev/null", os.O_WRONLY), 1)
        os.execvpe(sys.executable, [sys.executable, script, *argv], dict(os.environ, TERM="xterm"))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    scr, raw = Screen(rows, cols), b""

    def pump(sec):
        nonlocal raw
        end = time.time() + sec
        while time.time() < end:
            if select.select([fd], [], [], 0.05)[0]:
                try:
                    d = os.read(fd, 65536)
                except OSError:
                    return
                raw += d
                scr.feed(d.decode("utf-8", "replace"))
    deadline = time.time() + timeout
    while time.time() < deadline and "cochés".encode() not in raw:
        pump(0.1)
    pump(0.4)
    shots = [scr]
    import copy
    for k in keys:
        os.write(fd, k.encode())
        pump(0.35)
        shots.append(copy.deepcopy(scr))
    shots[0] = copy.deepcopy(shots[0])
    try:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
    except OSError:
        pass
    return shots


class HintHelpers(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(s.fit("abcdef", 10), "abcdef")
        self.assertEqual(s.fit("abcdef", 4), "abc…")
        self.assertEqual(len(s.fit("é" * 50, 20)), 20)

    def test_pick_hint_keeps_validate_and_cancel_at_every_width(self):
        for w in range(28, 200):
            h = s.pick_hint(s.HINTS, w)
            self.assertLessEqual(len(h), w, w)
            if w >= 32:
                self.assertIn("Entrée", h, w)
                self.assertIn("annuler", h, w)
        self.assertIn("naviguer", s.pick_hint(s.HINTS, 200))          # large : aide complète
        self.assertIn("Échap", s.pick_hint(s.FILTER_HINTS, 100, buf="ab"))
        self.assertIn("ab_", s.pick_hint(s.FILTER_HINTS, 100, buf="ab"))


@unittest.skipUnless(sys.platform.startswith("linux") and s.curses is not None, "pty/curses requis")
class InterfaceLayout(unittest.TestCase):
    """Ce qui s'affiche vraiment à l'écran (terminal émulé), pas seulement le résultat final."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.list = os.path.join(self.tmp, "l.txt")
        with open(self.list, "w") as f:
            f.write("alpha\nbruit publicitaire un\nbeta\nbruit publicitaire deux\ngamma\n")
        self.argv = ["--textlist", "-u", self.list, "-i", "--quiet", "--no-cache"]

    def test_layout_wide_terminal(self):
        scr = screens_after(self.argv, [], rows=14, cols=130)[0]
        lines = scr.lines()
        self.assertIn("5 entrées", lines[0])
        self.assertIn("5/5 cochés", lines[1])
        for i, word in enumerate(["alpha", "bruit publicitaire un", "beta", "bruit publicitaire deux", "gamma"]):
            self.assertIn(f"[x]", lines[2 + i])
            self.assertIn(word, lines[2 + i])
        self.assertIn("Entrée : valider", lines[-1])                   # 130 colonnes : aide complète tout en bas
        self.assertIn("Entrée valider", screens_after(self.argv, [], rows=14, cols=100)[0].lines()[-1])   # 100 : version condensée
        self.assertIn(self.list, "\n".join(lines))                    # détail de l'élément courant (la source)
        self.assertIn("reverse", scr.grid[2][3][1])                    # ligne courante en vidéo inverse
        self.assertNotIn("reverse", scr.grid[3][3][1])

    def test_cursor_and_checkbox_follow_keys(self):
        shots = screens_after(self.argv, [" ", "j", " "], rows=14, cols=100)   # décoche 1, descend, (déjà en 3) décoche 3
        after_space = shots[1].lines()
        self.assertIn("[ ]", after_space[2])                            # alpha décoché
        self.assertIn("4/5 cochés", after_space[1])
        self.assertIn("reverse", shots[1].grid[3][3][1])                # le curseur est descendu d'une ligne
        self.assertIn("reverse", shots[2].grid[4][3][1])
        self.assertIn("3/5 cochés", shots[3].lines()[1])

    def test_narrow_terminal_still_shows_validate_and_cancel(self):
        for cols in (60, 40):
            lines = screens_after(self.argv, [], rows=12, cols=cols)[0].lines()
            self.assertIn("Entrée", lines[-1], cols)
            self.assertIn("annuler", lines[-1], cols)
            self.assertTrue(all(len(l) <= cols for l in lines), cols)   # rien ne déborde

    def test_filter_screen_shows_only_matches_with_original_numbers(self):
        shots = screens_after(self.argv, ["/", "b", "r", "\r"], rows=12, cols=80)
        typing = shots[3].lines()
        self.assertIn("filtre : br_", typing[-1])                       # aide de saisie pendant le filtre
        final = shots[4].lines()
        self.assertIn("2 affichés", final[1])
        self.assertIn("filtre : br", final[1])
        rows = [l for l in final[2:7] if l.strip()]
        self.assertEqual(len(rows), 2)                                  # aucune ligne fantôme
        self.assertTrue(rows[0].strip().startswith("[x]    2."))        # numéros d'origine conservés
        self.assertTrue(rows[1].strip().startswith("[x]    4."))
        self.assertIn("Entrée", final[-1])                              # l'aide de navigation est de retour

    def test_long_labels_are_ellipsized_not_wrapped(self):
        long = os.path.join(self.tmp, "long.txt")
        with open(long, "w") as f:
            f.write("x" * 300 + "\nautre\n")
        lines = screens_after(["--textlist", "-u", long, "-i", "--quiet", "--no-cache"], [], rows=10, cols=50)[0].lines()
        self.assertTrue(lines[2].endswith("…"))
        self.assertTrue(all(len(l) <= 50 for l in lines))


class ExportSafety(unittest.TestCase):
    """Le contenu exporté vient du web (non fiable) : pas de formule, pas de HTML/Markdown injecté, pas de lien javascript:."""

    HOSTILE = {"searches": [
        {"title": "Python (programming language) [wiki]", "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
         "snippet": "x", "query": "q", "engine": "e"},
        {"title": '=HYPERLINK("http://evil.example","clic")', "url": "https://a.org/1", "snippet": "", "query": "q", "engine": "e"},
        {"title": "+cmd|' /C calc'!A0", "url": "https://a.org/2", "snippet": "", "query": "q", "engine": "e"},
        {"title": "<img src=x onerror=alert(1)>", "url": "javascript:alert(1)", "snippet": "<script>alert(1)</script>",
         "query": "q", "engine": "e"}], "pages": []}

    def setUp(self):
        setup_args()
        self.tmp = tempfile.mkdtemp()

    def out(self, ext, data=None):
        path = os.path.join(self.tmp, "o" + ext)
        s.save(path, data or self.HOSTILE)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_csv_neutralises_formulas(self):
        import csv as _csv
        rows = list(_csv.reader(io.StringIO(self.out(".csv"))))
        texts = [r[2] for r in rows[1:]]
        self.assertEqual(texts[1], "'=HYPERLINK(\"http://evil.example\",\"clic\")")
        self.assertEqual(texts[2], "'+cmd|' /C calc'!A0")
        self.assertEqual(texts[0], "Python (programming language) [wiki]")           # texte normal inchangé
        for r in rows[1:]:
            self.assertNotIn(r[2][:1], "=+-@")

    def test_csv_raw_flag_disables_it(self):
        s.ARGS.csv_raw = True
        self.assertIn("=HYPERLINK", self.out(".csv").split("\n")[2].split(",")[2])
        self.assertFalse(s.csv_safe("=1").startswith("'"))

    def test_csv_safe_unit(self):
        for bad in ("=1+1", "+1", "-1", "@SUM", "\tx", "\rx"):
            self.assertEqual(s.csv_safe(bad), "'" + bad)
        for ok in ("abc", "", "1=1", " =x", 42):
            self.assertEqual(s.csv_safe(ok), ok)

    def test_markdown_escapes_and_encodes(self):
        md = self.out(".md").split("\n")
        self.assertIn("\\[wiki\\]", md[0])                                              # crochets échappés
        self.assertIn("Python_%28programming_language%29)", md[0])                        # parenthèses de l'URL encodées
        self.assertIsNone(_re.search(r"(?<!\\)[<>]", md[3]))                             # aucun < > non échappé : pas de HTML brut
        self.assertIsNone(_re.search(r"(?<!\\)\]\(", md[3]))                              # aucun lien construit sur la ligne hostile
        self.assertEqual(_re.findall(r"(?<!\\)\]\(([^)]*)", "\n".join(md)).count("javascript:alert(1"), 0)   # jamais un lien javascript:

    def test_html_escapes_and_drops_unsafe_links(self):
        html = self.out(".html")
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("javascript:", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn('rel="noopener noreferrer nofollow"', html)
        self.assertIn('href="https://en.wikipedia.org/wiki/Python_(programming_language)"', html)

    def test_textlist_exports_are_safe_too(self):
        tl = {"sources": [], "count": 3, "items": [{"line": "[clic](javascript:alert(1))", "source": "u"},
                                                   {"line": "=SUM(A1:A9)", "source": "u"}, {"line": "<b>x</b>", "source": "u"}]}
        for ext in (".md", ".csv", ".html"):
            path = os.path.join(self.tmp, "t" + ext)
            s.save_textlist(path, tl)
        with open(os.path.join(self.tmp, "t.md")) as f:
            md = f.read()
        self.assertIsNone(_re.search(r"(?<!\\)\]\(", md))                                 # pas de lien Markdown actif
        self.assertIn("\\[clic\\]", md)
        self.assertIsNone(_re.search(r"(?<!\\)<", md))                                   # pas de HTML brut
        with open(os.path.join(self.tmp, "t.csv")) as f:
            self.assertIn("u,'=SUM(A1:A9)", f.read())
        with open(os.path.join(self.tmp, "t.html")) as f:
            self.assertIn("&lt;b&gt;x&lt;/b&gt;", f.read())


def urllib_unquote(x):
    import urllib.parse
    return urllib.parse.unquote(x)


class Completion(unittest.TestCase):
    def setUp(self):
        s.ARGS, self.ap = s.parse_args(["-q", "x", "--quiet", "--no-searx"])
        self.script = s.completion_script(self.ap)

    def test_every_parser_option_is_completed(self):
        for a in self.ap._actions:
            for o in a.option_strings:
                self.assertIn(o, self.script, o)                       # généré depuis le parseur : rien ne manque

    def test_values_come_from_the_code(self):
        for name in list(s.ENGINES) + ["auto", "all"]:
            self.assertIn(name, self.script)
        for dom in s.PASTE_DOMAINS:
            self.assertIn(dom, self.script)
        self.assertIn("compgen -f", self.script)                       # fichiers pour -o / -f / --config

    @unittest.skipUnless(s.shutil.which("bash"), "bash absent")
    def test_script_is_valid_bash_and_completes(self):
        import subprocess
        path = os.path.join(tempfile.mkdtemp(), "c.sh")
        with open(path, "w") as f:
            f.write(self.script)
        self.assertEqual(subprocess.run(["bash", "-n", path]).returncode, 0)
        def complete(words):
            cmd = f"source {path}; COMP_WORDS=({words}); COMP_CWORD={len(words.split()) - 1}; _scrapaud; echo \"${{COMPREPLY[*]}}\""
            return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True).stdout.split()
        self.assertEqual(set(complete("scrapaud --wl-s")), {"--wl-sort", "--wl-split", "--wl-stopwords"})
        self.assertEqual(complete("scrapaud -e b"), ["bing"])
        self.assertEqual(complete("scrapaud --as d"), ["domains"])
        self.assertEqual(complete("scrapaud --doc"), ["--doctor"])


class PasteDir(unittest.TestCase):
    """--paste-dir : un .txt par paste (contenu complet), classé site/date, index.md, droits privés, jamais hors du dossier."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "pastes")
        setup_args("--pastebin", "--paste-dir", self.root)

    def rec(self, url="https://pastebin.com/AbCdEfGh", title="Mon paste", **kw):
        r = {"type": "paste", "url": url, "raw_url": url.replace(".com/", ".com/raw/"), "site": s.host(url), "title": title,
             "size": 0, "matches": []}
        r.update(kw)
        return r

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_layout_header_and_full_content(self):
        body = "ligne\n" * 5000                                            # 30 000 o : plus que --paste-content (20 000)
        path = s.save_paste_file(self.rec(syntax="python", posted="2 days ago"), body)
        day = __import__("datetime").datetime.now().strftime("%Y%m%d")
        self.assertEqual(path, os.path.join(self.root, "pastebin-com", day, "AbCdEfGh_mon-paste.txt"))
        text = self.read(path)
        for expected in ("source   : https://pastebin.com/AbCdEfGh", "brut     : https://pastebin.com/raw/AbCdEfGh",
                         "titre    : Mon paste", "syntaxe  : python", "publié   : 2 days ago", "taille   : 30000 o"):
            self.assertIn(expected, text)
        self.assertTrue(text.endswith(body))                             # contenu complet, intact, après l'en-tête
        self.assertEqual(text.count("ligne\n"), 5000)

    def test_private_permissions(self):
        path = s.save_paste_file(self.rec(), "secret possible\n")
        self.assertEqual(oct(os.stat(path).st_mode)[-3:], "600")
        for d in (self.root, os.path.dirname(os.path.dirname(path)), os.path.dirname(path)):
            self.assertEqual(oct(os.stat(d).st_mode)[-3:], "700", d)
        self.assertEqual(oct(os.stat(os.path.join(self.root, "index.md")).st_mode)[-3:], "600")

    def test_index_is_safe_markdown_with_relative_links(self):
        s.save_paste_file(self.rec(title="Titre [x](javascript:alert(1)) <b>gras</b>", matches=["a", "b"]), "x")
        idx = self.read(os.path.join(self.root, "index.md"))
        self.assertTrue(idx.startswith("# Pastes récupérés par scrapaud\n\n"))
        self.assertNotIn("\\n", idx)                                      # de vrais retours à la ligne, pas de « \n » littéral
        self.assertIsNone(re.search(r"(?<!\\)<", idx))                    # pas de HTML brut
        self.assertNotIn("](javascript", idx.replace("\\]", ""))         # pas de lien actif javascript:
        link = re.search(r"\]\(([^)]+\.txt)\)", idx).group(1)
        self.assertTrue(os.path.isfile(os.path.join(self.root, urllib_unquote(link))))   # lien relatif valide
        self.assertIn("2 correspondance(s)", idx)

    def test_same_paste_twice_is_not_duplicated_but_name_clash_gets_suffix(self):
        first = s.save_paste_file(self.rec(), "un")
        again = s.save_paste_file(self.rec(), "un")
        self.assertEqual(first, again)
        self.assertEqual(len(os.listdir(os.path.dirname(first))), 1)
        self.assertEqual(self.read(os.path.join(self.root, "index.md")).count("\n- "), 1)   # une seule ligne d'index
        other = s.save_paste_file(self.rec(url="https://pastebin.com/AbCdEfGh?x=1", title="Mon paste"), "deux")  # même nom, autre source
        self.assertTrue(other.endswith("-2.txt"))
        self.assertEqual(self.read(first).split("-" * 64 + "\n")[1], "un\n")               # le 1er n'est pas écrasé

    def test_hostile_titles_and_ids_stay_inside_the_folder(self):
        for url, title in (("https://pastebin.com/..%2F..%2Fetc%2Fpasswd", "../../../etc/passwd"),
                           ("https://pastebin.com/a/../../b", "/etc/cron.d/evil"),
                           ("https://pastebin.com/AbC", "x" * 500), ("https://pastebin.com/", ""), ("https://évil.example/é", "É‮\x00")):
            path = s.save_paste_file(self.rec(url=url, title=title), "x")
            self.assertTrue(os.path.realpath(path).startswith(os.path.realpath(self.root) + os.sep), (url, title))
            self.assertNotIn("..", os.path.relpath(path, self.root).split(os.sep))
            self.assertLessEqual(len(os.path.basename(path)), 120)
        outside = [f for f in os.listdir(self.tmp) if f != "pastes"]
        self.assertEqual(outside, [])                                    # rien créé à côté du dossier choisi

    def test_disk_guard_writes_nothing(self):
        orig = s.free_space
        s.free_space = lambda p: 1024
        try:
            self.assertIsNone(s.save_paste_file(self.rec(), "x" * 100))
            self.assertFalse(os.path.exists(self.root))                   # ni dossier, ni index
        finally:
            s.free_space = orig

    def test_scrape_paste_saves_full_body_even_with_small_paste_content(self):
        s.ARGS.paste_content = 10
        body = "abcdefghij" * 50
        orig = s.fetch_c
        s.fetch_c = lambda url, **kw: (body, url, "text/plain")
        try:
            rec = s.scrape_paste("https://pastebin.com/ZzZzZzZz", "Titre")
        finally:
            s.fetch_c = orig
        self.assertEqual(len(rec["content"]), 10)                         # affichage/JSON tronqués
        self.assertTrue(self.read(rec["file"]).endswith(body + "\n"))     # fichier complet
        self.assertEqual(rec["size"], 500)

    def test_filtered_pastes_are_not_saved_and_flag_off_saves_nothing(self):
        orig = s.fetch_c
        s.fetch_c = lambda url, **kw: ("rien d'intéressant", url, "text/plain")
        try:
            s.ARGS._grep = re.compile("motcle")
            self.assertIsNone(s.scrape_paste("https://pastebin.com/AbCdEfGh", "t"))   # écarté par --grep : rien écrit
            self.assertFalse(os.path.exists(self.root))
            s.ARGS._grep, s.ARGS.paste_dir = None, None
            rec = s.scrape_paste("https://pastebin.com/AbCdEfGh", "t")                 # option absente : aucun fichier
            self.assertNotIn("file", rec)
            self.assertFalse(os.path.exists(self.root))
        finally:
            s.fetch_c = orig

    def test_default_dir_when_flag_has_no_value(self):
        self.assertEqual(s.parse_args(["--pastebin", "--paste-dir", "--no-searx"])[0].paste_dir, "~/pastes/scrapaud")
        self.assertIsNone(s.parse_args(["--pastebin", "--no-searx"])[0].paste_dir)


class AuthenticatedRequests(unittest.TestCase):
    """Une page obtenue avec une session ne doit ni finir dans le cache, ni être resservie sans cookie ; secrets hors de `ps`."""

    def setUp(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(inner):
                priv = "sid=" in (inner.headers.get("Cookie") or "") or bool(inner.headers.get("X-Token"))
                body = ("PAGE PRIVEE solde 1234" if priv else "page publique").encode()
                inner.send_response(200)
                inner.send_header("Content-Type", "text/plain")
                inner.end_headers()
                inner.wfile.write(body)
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/compte"
        self.cache = tempfile.mkdtemp()
        s.CACHE_DIR = self.cache

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def run_fetch(self, *argv):
        s.ARGS, _ = s.parse_args(["-q", "x", "--quiet", "--no-searx", "--allow-private", "--delay", "0", *argv])
        s._opener = s.build_opener(None)
        s.setup_security([self.url] if ("--cookie" in argv or "-H" in argv) else [])
        return s.fetch_c(self.url)[0]

    def cache_text(self):
        import glob
        import gzip
        return " ".join(gzip.open(f, "rt").read() for f in glob.glob(self.cache + "/*.json.gz"))

    def test_cookie_page_is_not_cached_nor_served_to_a_cookieless_run(self):
        self.assertEqual(self.run_fetch("--cookie", "sid=42"), "PAGE PRIVEE solde 1234")
        self.assertNotIn("PRIVEE", self.cache_text())                     # rien de privé sur le disque
        self.assertEqual(self.run_fetch(), "page publique")               # le run suivant sans cookie voit la page publique

    def test_custom_header_page_is_not_cached_either(self):
        self.assertEqual(self.run_fetch("-H", "X-Token: abc"), "PAGE PRIVEE solde 1234")
        self.assertNotIn("PRIVEE", self.cache_text())
        self.assertEqual(self.run_fetch(), "page publique")

    def test_public_pages_are_still_cached(self):
        self.assertEqual(self.run_fetch(), "page publique")
        self.assertIn("page publique", self.cache_text())                 # le cache normal fonctionne toujours

    def test_cookie_not_in_scope_keeps_using_cache(self):
        s.ARGS, _ = s.parse_args(["-q", "x", "--quiet", "--no-searx", "--allow-private", "--delay", "0", "--cookie", "sid=1",
                                  "--cookie-domain", "autre.example"])
        s._opener = s.build_opener(None)
        s.setup_security([self.url])
        self.assertEqual(s.fetch_c(self.url)[0], "page publique")         # le cookie ne part pas vers cet hôte : requête publique
        self.assertIn("page publique", self.cache_text())                 # donc mise en cache normalement


class SecretArguments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def write(self, name, text, mode=0o600):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, mode)
        return path

    def test_cookie_from_file_keeps_it_out_of_the_command_line(self):
        path = self.write("c.txt", "sid=SECRETVALUE\n")
        a, _ = s.parse_args(["-q", "x", "--no-searx", "--cookie", "@" + path])
        self.assertEqual(a.cookie, "sid=SECRETVALUE")                     # espace final retiré

    def test_cookie_from_environment(self):
        old = os.environ.get("SCRAPAUD_COOKIE")
        os.environ["SCRAPAUD_COOKIE"] = "sid=ENV"
        try:
            self.assertEqual(s.parse_args(["-q", "x", "--no-searx"])[0].cookie, "sid=ENV")
            self.assertEqual(s.parse_args(["-q", "x", "--no-searx", "--cookie", "sid=CLI"])[0].cookie, "sid=CLI")   # la ligne de commande prime
        finally:
            os.environ.pop("SCRAPAUD_COOKIE", None)
            if old is not None:
                os.environ["SCRAPAUD_COOKIE"] = old

    def test_header_file_gives_one_header_per_line(self):
        path = self.write("h.txt", "Authorization: Bearer abc\nX-Token: 1\n\n")
        a, _ = s.parse_args(["-q", "x", "--no-searx", "-H", "@" + path, "-H", "Accept: text/plain"])
        self.assertEqual(a.header, ["Authorization: Bearer abc", "X-Token: 1", "Accept: text/plain"])

    def test_missing_secret_file_is_a_clear_error(self):
        with self.assertRaises(SystemExit) as cm:
            s.parse_args(["-q", "x", "--no-searx", "--cookie", "@/inexistant/cookie.txt"])
        self.assertIn("illisible", str(cm.exception))

    def test_world_readable_secret_file_warns(self):
        path = self.write("open.txt", "sid=1", mode=0o644)
        err, old = io.StringIO(), sys.stderr
        sys.stderr = err
        try:
            s.parse_args(["-q", "x", "--no-searx", "--cookie", "@" + path])
        finally:
            sys.stderr = old
        self.assertIn("lisible par d'autres", err.getvalue())
        err = io.StringIO()
        sys.stderr = err
        try:
            s.parse_args(["-q", "x", "--no-searx", "--cookie", "@" + self.write("ok.txt", "sid=1", mode=0o600)])
        finally:
            sys.stderr = old
        self.assertEqual(err.getvalue(), "")                              # 600 : aucun avertissement

    def test_plain_values_are_untouched(self):
        a, _ = s.parse_args(["-q", "x", "--no-searx", "--cookie", "a=b; c=d", "-H", "X: y"])
        self.assertEqual((a.cookie, a.header), ("a=b; c=d", ["X: y"]))

    def test_render_warns_that_cookie_is_not_sent(self):
        setup_args("--render", "--cookie", "sid=1")
        s.ARGS.quiet = False
        err, old = io.StringIO(), sys.stderr
        sys.stderr = err
        try:
            s.setup_security(["https://exemple.org/"])
        finally:
            sys.stderr = old
        self.assertIn("PAS transmis au rendu", err.getvalue())


class HostilePages(unittest.TestCase):
    """L'outil lit des pages qu'il ne contrôle pas : imbrication infinie ou pages géantes ne doivent pas le geler."""

    def setUp(self):
        setup_args()

    def timed_parse(self, html):
        p = s.PageParser("https://ex.org/")
        t0 = time.time()
        p.feed(html)
        return p, time.time() - t0

    def test_deep_nesting_is_linear_not_quadratic(self):
        n = 40000                                                     # ~800 Ko ; avant correctif : ~25 s (quadratique)
        p, dt = self.timed_parse("<div>" * n + "".join(f"<p>texte {i}</p>" for i in range(n)))
        self.assertLess(dt, 6.0, f"{dt:.1f}s")
        self.assertLessEqual(len(p._stk), s.MAX_DEPTH)                # la pile suivie est bornée
        self.assertEqual(len(p.pieces), n)                            # le texte est quand même récupéré

    def test_nested_lists_are_bounded(self):
        p, dt = self.timed_parse("<ul><li>a" * 30000)
        self.assertLess(dt, 4.0)
        self.assertLessEqual(len(p._lstack), s.MAX_LIST_DEPTH)

    def test_legitimate_deep_page_still_parsed_correctly(self):
        html = ("<main>" + "<div>" * 150 + "<p>Un long paragraphe de contenu réel qui doit rester conservé malgré la profondeur.</p>"
                + "</div>" * 150 + "</main><footer><p>© pied de page qui doit rester exclu du contenu principal</p></footer>")
        p, _ = self.timed_parse(html)
        self.assertEqual(p.main_pieces(), ["Un long paragraphe de contenu réel qui doit rester conservé malgré la profondeur."])

    def test_unclosed_and_stray_tags_do_not_crash(self):
        for html in ("</div></div></p></li>" * 1000, "<" * 5000, "<a href=" * 2000, "<p>" + "&" * 10000, "<!--" * 3000,
                     "<table><tr><td>" * 3000, "\x00" * 5000):
            p, dt = self.timed_parse(html)
            self.assertLess(dt, 3.0)


class EchoServer(threading.Thread):
    """Serveur TCP qui envoie « hello » à la connexion."""

    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.start()

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            c.sendall(b"hello")
            c.close()


def proxy_request(port, payload, read=4096):
    c = socket.create_connection(("127.0.0.1", port), timeout=8)
    c.sendall(payload)
    data = b""
    try:
        while len(data) < read:
            d = c.recv(read)
            if not d:
                break
            data += d
    except socket.timeout:
        pass
    c.close()
    return data


class GuardProxyTests(unittest.TestCase):
    """Le proxy local par lequel passe TOUT le trafic de Chromium (--render)."""

    def setUp(self):
        setup_args()
        s.ARGS.allow_private = False
        s.ARGS._trusted = set()
        self.echo = EchoServer()
        self.proxy = s.GuardProxy()

    def tearDown(self):
        self.proxy.close()
        self.echo.sock.close()

    def test_connect_to_private_address_is_refused_and_recorded(self):
        data = proxy_request(self.proxy.port, f"CONNECT 127.0.0.1:{self.echo.port} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        self.assertTrue(data.startswith(b"HTTP/1.1 403"), data)
        self.assertNotIn(b"hello", data)
        self.assertEqual(self.proxy.blocked, ["127.0.0.1"])

    def test_connect_to_trusted_host_is_tunnelled(self):
        s.ARGS._trusted = {"127.0.0.1"}
        data = proxy_request(self.proxy.port, f"CONNECT 127.0.0.1:{self.echo.port} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        self.assertTrue(data.startswith(b"HTTP/1.1 200"), data)
        self.assertIn(b"hello", data)
        self.assertEqual(self.proxy.blocked, [])

    def test_allow_private_lifts_the_filter(self):
        s.ARGS.allow_private = True
        data = proxy_request(self.proxy.port, f"CONNECT 127.0.0.1:{self.echo.port} HTTP/1.1\r\n\r\n".encode())
        self.assertIn(b"hello", data)

    def test_plain_http_absolute_uri(self):
        srv = MiniServer({"/hello": ("text/plain", "bonjour direct")})
        try:
            url = f"http://127.0.0.1:{srv.srv.server_port}/hello"
            req = f"GET {url} HTTP/1.1\r\nHost: 127.0.0.1\r\nProxy-Connection: keep-alive\r\n\r\n".encode()
            self.assertTrue(proxy_request(self.proxy.port, req).startswith(b"HTTP/1.1 403"))      # non demandé : refusé
            s.ARGS._trusted = {"127.0.0.1"}
            data = proxy_request(self.proxy.port, req)
            self.assertIn(b"200 OK", data.split(b"\r\n")[0] + b"")
            self.assertIn(b"bonjour direct", data)
        finally:
            srv.close()

    def test_malformed_requests_do_not_kill_the_proxy(self):
        for junk in (b"\r\n\r\n", b"GARBAGE\r\n\r\n", b"CONNECT :99999999 HTTP/1.1\r\n\r\n", b"\x00" * 100 + b"\r\n\r\n"):
            proxy_request(self.proxy.port, junk, read=1)
        s.ARGS._trusted = {"127.0.0.1"}
        data = proxy_request(self.proxy.port, f"CONNECT 127.0.0.1:{self.echo.port} HTTP/1.1\r\n\r\n".encode())
        self.assertIn(b"hello", data)                                                   # toujours en vie

    def test_tor_mode_goes_through_socks_and_refuses_private_literals(self):
        fake = FakeSocks()
        s.ARGS.tor_proxy = f"127.0.0.1:{fake.port}"
        tor = s.GuardProxy(tor=True)
        try:
            data = proxy_request(tor.port, b"CONNECT abcdefghij234567.onion:80 HTTP/1.1\r\n\r\n")
            self.assertTrue(data.startswith(b"HTTP/1.1 200"))
            c = socket.create_connection(("127.0.0.1", tor.port), timeout=8)              # 2e connexion pour la requête réelle
            c.close()
            fake.join(3)
            self.assertEqual(fake.requested, "abcdefghij234567.onion")                   # nom transmis à Tor, pas résolu ici
            self.assertEqual(proxy_request(tor.port, b"CONNECT 10.0.0.5:80 HTTP/1.1\r\n\r\n")[:12], b"HTTP/1.1 403")
            self.assertEqual(proxy_request(tor.port, b"CONNECT localhost:80 HTTP/1.1\r\n\r\n")[:12], b"HTTP/1.1 403")
        finally:
            tor.close()

    def test_socks_refuses_private_targets_unless_allowed(self):
        s.ARGS.allow_private = False
        for host in ("127.0.0.1", "localhost", "192.168.1.1", "169.254.169.254", "x.localhost"):
            with self.assertRaises(OSError) as cm:
                s.socks5_connect(("127.0.0.1", 1), host, 80, 1)
            self.assertIn("adresse privée bloquée", str(cm.exception), host)
        s.ARGS.allow_private = True
        with self.assertRaises(OSError) as cm:
            s.socks5_connect(("127.0.0.1", 1), "127.0.0.1", 80, 1)
        self.assertNotIn("bloquée", str(cm.exception))                                   # autorisé : l'échec est juste « connexion refusée »


@unittest.skipUnless(s.shutil.which("chromium") or s.shutil.which("flatpak"), "navigateur requis")
class RenderThroughGuardProxy(unittest.TestCase):
    """Vrai Chromium : sa page ne peut plus lire un service local qu'on n'a pas demandé."""

    def setUp(self):
        setup_args("--render", "--render-wait", "3")           # d'abord : find_browser()/render_selftest() lisent ARGS
        try:
            ok, _ = s.render_selftest()                        # le navigateur sait-il vraiment rendre une page ICI ?
        except ValueError:
            self.skipTest("aucun Chromium")
        if not ok:
            self.skipTest("Chromium présent mais inutilisable dans cet environnement (HOME/XDG absents, pas d'affichage…)")
        s.ARGS.allow_private = False
        self.secret = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._secret_handler())
        threading.Thread(target=self.secret.serve_forever, daemon=True).start()
        port = self.secret.server_port
        js = ('var o=document.getElementById("o");o.textContent="script-propre-charge";'
              f'fetch("http://localhost:{port}/secret").then(function(r){{return r.text()}})'
              '.then(function(t){o.textContent+=" | LU:"+t}).catch(function(e){o.textContent+=" | BLOQUE"});')
        self.page = MiniServer({"/p.html": ("text/html", '<html><body><div id="o"></div><script src="/a.js"></script></body></html>'),
                                "/a.js": ("application/javascript", js)})
        self.url = f"{self.page.url}/p.html"
        s.ARGS._trusted = {"127.0.0.1"}                     # comme un -u explicite ; « localhost » n'est PAS demandé

    def tearDown(self):
        self.secret.shutdown()
        self.secret.server_close()
        self.page.close()

    @staticmethod
    def _secret_handler():
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(inner):
                inner.send_response(200)
                inner.send_header("Access-Control-Allow-Origin", "*")
                inner.send_header("Content-Type", "text/plain")
                inner.end_headers()
                inner.wfile.write(b"SERVICE-INTERNE-SECRET")
        return H

    def test_page_script_cannot_read_untrusted_local_service(self):
        dom = s.render_dom(self.url)
        self.assertIn("script-propre-charge", dom)          # la page et son script fonctionnent (via le proxy)
        self.assertIn("BLOQUE", dom)
        self.assertNotIn("SERVICE-INTERNE-SECRET", dom)

    def test_allow_private_lets_it_through(self):
        s.ARGS.allow_private = True
        dom = s.render_dom(self.url)
        self.assertIn("LU:SERVICE-INTERNE-SECRET", dom)


class ProxyDestinationGuardTests(unittest.TestCase):
    """--proxy : la destination n'est plus vue à la connexion ; contrôle préalable à chaque saut."""

    def setUp(self):
        setup_args()
        s.ARGS.allow_private = False
        s.ARGS._trusted = set()
        self.opener = s.build_opener("http://127.0.0.1:1")            # proxy mort : un contrôle réussi échouerait sur « refusé »
        self.orig = s.socket.getaddrinfo

    def tearDown(self):
        s.socket.getaddrinfo = self.orig

    def attempt(self, url):
        try:
            self.opener.open(url, timeout=3)
        except urllib.error.URLError as e:
            return str(e.reason)
        return "ok"

    def test_private_literals_and_localhost_are_refused_before_the_proxy(self):
        for url in ("http://192.168.1.10/", "http://10.0.0.5:8080/x", "http://169.254.169.254/latest/", "http://localhost/", "http://[::1]/"):
            self.assertIn("adresse privée bloquée", self.attempt(url), url)

    def test_name_resolving_to_private_address_is_refused(self):
        s.socket.getaddrinfo = lambda h, *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))]
        self.assertIn("adresse privée bloquée", self.attempt("http://interne.example/"))

    def test_public_name_reaches_the_proxy_step(self):
        s.socket.getaddrinfo = lambda h, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))]
        self.assertNotIn("bloquée", self.attempt("http://exemple.org/"))      # passe le contrôle ; échoue ensuite sur le proxy mort

    def test_localhost_names_are_refused_even_when_dns_cannot_confirm(self):
        def boom(*a, **k):
            raise OSError("no dns")
        s.socket.getaddrinfo = boom                                          # aucune résolution possible ici
        for url in ("http://localhost/", "http://x.localhost/", "http://api.localhost:8080/"):
            self.assertIn("adresse privée bloquée", self.attempt(url), url)   # la règle « nom local » suffit, sans DNS

    def test_unresolvable_name_is_left_to_the_proxy(self):
        def boom(*a, **k):
            raise OSError("no dns")
        s.socket.getaddrinfo = boom
        self.assertNotIn("bloquée", self.attempt("http://interne-au-proxy.example/"))

    def test_trusted_host_and_allow_private_pass(self):
        s.ARGS._trusted = {"192.168.1.10"}
        self.assertNotIn("bloquée", self.attempt("http://192.168.1.10/"))
        s.ARGS._trusted = set()
        s.ARGS.allow_private = True
        self.assertNotIn("bloquée", self.attempt("http://10.0.0.5/"))


class RobotsModes(unittest.TestCase):
    def setUp(self):
        self.srv = MiniServer({"/robots.txt": ("text/plain", "User-agent: *\nDisallow: /prive/\n"),
                               "/prive/a": ("text/plain", "a"), "/pub/b": ("text/plain", "b")})
        self.base = self.srv.url
        s._robots.clear()

    def tearDown(self):
        self.srv.close()
        s._robots.clear()

    def check(self, url, *argv, explicit=()):
        setup_args(*argv)
        s.setup_security(list(explicit))
        return s.allowed_by_robots(url)

    def test_default_auto_respects_robots_for_discovered_pages_only(self):
        typed = f"{self.base}/prive/a"
        self.assertTrue(self.check(typed, explicit=[typed]))                       # URL tapée par l'utilisateur : autorisée
        s._robots.clear()
        self.assertFalse(self.check(f"{self.base}/prive/a"))                       # même URL DÉCOUVERTE (lien/résultat) : refusée
        self.assertTrue(self.check(f"{self.base}/pub/b"))

    def test_forced_modes(self):
        typed = f"{self.base}/prive/a"
        self.assertFalse(self.check(typed, "--robots", explicit=[typed]))          # --robots : toujours
        s._robots.clear()
        self.assertTrue(self.check(f"{self.base}/prive/a", "--no-robots"))         # --no-robots : jamais

    def test_flag_default_is_auto_and_fragment_ignored(self):
        self.assertIsNone(s.parse_args(["-q", "x", "--no-searx"])[0].robots)
        self.assertTrue(s.parse_args(["-q", "x", "--no-searx", "--robots"])[0].robots)
        self.assertFalse(s.parse_args(["-q", "x", "--no-searx", "--no-robots"])[0].robots)
        typed = f"{self.base}/prive/a"
        self.assertTrue(self.check(typed + "#ancre", explicit=[typed]))            # ancre ignorée pour la comparaison

    def test_missing_robots_txt_allows_everything(self):
        srv = MiniServer({})
        try:
            self.assertTrue(self.check(f"{srv.url}/n-importe-quoi"))
        finally:
            srv.close()


class StopwordLanguages(unittest.TestCase):
    TEXT = {"fr": "Le chat dort sur le canapé et la souris regarde par la fenêtre pendant que les enfants jouent dans le jardin avec leurs amis du quartier",
            "en": "The cat sleeps on the sofa and the mouse looks through the window while the children play in the garden with their friends from the neighbourhood",
            "de": "Die Katze schläft auf dem Sofa und die Maus schaut durch das Fenster während die Kinder im Garten mit ihren Freunden aus der Nachbarschaft spielen",
            "es": "El gato duerme en el sofá y el ratón mira por la ventana mientras los niños juegan en el jardín con sus amigos del barrio y con todos",
            "it": "Il gatto dorme sul divano e il topo guarda dalla finestra mentre i bambini giocano nel giardino con i loro amici del quartiere che sono"}

    def setUp(self):
        setup_args("--wordlist", "--wl-stopwords", "auto")

    def test_five_languages_detected(self):
        for lang, text in self.TEXT.items():
            self.assertEqual(s.detect_language(s.word_regex().findall(text)), lang)

    def test_tiny_snippets_are_never_classified(self):
        # 10 mots vides français seulement : sans la garde de longueur minimale, « fr » serait détecté sur un titre de 3 mots
        self.assertIsNone(s.detect_language(["le", "la", "les", "de", "du", "des", "un", "une", "et", "ou"]))
        self.assertIsNone(s.detect_language(["Le", "Monde"]))
        # texte court -> langue inconnue -> AUCUN mot vide retiré (on préfère garder trop que perdre des mots)
        self.assertEqual(s.tokenize("Les chats aiment les souris"), ["Les", "chats", "aiment", "les", "souris"])

    def test_uncertain_texts_are_not_filtered(self):
        self.assertIsNone(s.detect_language(s.word_regex().findall("kernel panic nginx redis")))            # trop court
        self.assertIsNone(s.detect_language(s.word_regex().findall("kernel panic nginx redis " * 10)))      # assez long mais aucun mot vide
        self.assertEqual(s.tokenize("kernel panic nginx redis"), ["kernel", "panic", "nginx", "redis"])

    def test_auto_filters_per_source_language(self):
        fr = s.tokenize(self.TEXT["fr"])
        self.assertNotIn("dans", fr)
        self.assertNotIn("avec", fr)
        self.assertIn("canapé", fr)
        en = s.tokenize(self.TEXT["en"])
        self.assertNotIn("with", en)
        self.assertNotIn("through", en)
        self.assertIn("neighbourhood", en)
        self.assertIn("dans", s.tokenize(self.TEXT["en"] + " dans"))       # « dans » n'est pas un mot vide anglais : gardé

    def test_explicit_lists_and_validation(self):
        a, _ = s.parse_args(["-q", "x", "--no-searx", "--wl-stopwords", "fr,de"])
        self.assertTrue(a._wl_stop >= s.STOPWORDS["fr"] and a._wl_stop >= s.STOPWORDS["de"])
        self.assertFalse(a._wl_auto)
        self.assertTrue(s.parse_args(["-q", "x", "--no-searx", "--wl-stopwords", "auto"])[0]._wl_auto)
        old, sys.stderr = sys.stderr, io.StringIO()
        try:
            with self.assertRaises(SystemExit):
                s.parse_args(["-q", "x", "--no-searx", "--wl-stopwords", "klingon"])
        finally:
            sys.stderr = old

    def test_lists_are_substantial(self):
        for lang, minimum in (("fr", 200), ("en", 120), ("de", 120), ("es", 90), ("it", 80)):
            self.assertGreaterEqual(len(s.STOPWORDS[lang]), minimum, lang)


class TableColumns(unittest.TestCase):
    HTML = ("<table><tr><th>Drapeau</th><th>Code</th><th>Pays</th><th>Population</th></tr>"
            "<tr><td></td><td>250</td><td>France</td><td>68000000</td></tr>"
            "<tr><td></td><td>276</td><td>Allemagne</td><td>84000000</td></tr>"
            "<tr><td></td><td>380</td><td>Italie</td><td>59000000</td></tr>"
            "<tr><td></td><td>724</td><td>Espagne</td><td>48000000</td></tr></table>")

    def setUp(self):
        setup_args()

    def parse(self, html):
        p = s.PageParser("https://ex.org/")
        p.feed(html)
        return p

    def test_header_rows_are_detected(self):
        p = self.parse(self.HTML)
        self.assertEqual(p.table_headers, [[True, False, False, False, False]])

    def test_best_column_skips_flags_codes_numbers_and_headers(self):
        p = self.parse(self.HTML)
        self.assertEqual(s.best_column(p.tables, p.table_headers), ["France", "Allemagne", "Italie", "Espagne"])

    def test_nothing_clear_returns_empty(self):
        p = self.parse("<table><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr><tr><td>5</td><td>6</td></tr></table>")
        self.assertEqual(s.best_column(p.tables, p.table_headers), [])              # que des nombres
        p = self.parse("<table><tr><td>Paris</td></tr><tr><td>Lyon</td></tr></table>")
        self.assertEqual(s.best_column(p.tables, p.table_headers), [])              # moins de 3 lignes de données

    def test_picks_the_richest_table(self):
        p = self.parse("<table><tr><td>a</td></tr><tr><td>b</td></tr><tr><td>c</td></tr></table>" + self.HTML)
        self.assertEqual(s.best_column(p.tables, p.table_headers)[0], "France")

    def test_textlist_from_table_uses_the_best_column(self):
        srv = MiniServer({"/t.html": ("text/html", "<html><body>" + self.HTML + "</body></html>")})
        try:
            s.ARGS.text_from = "table"
            self.assertEqual(s.raw_text_lines(srv.url + "/t.html"), ["France", "Allemagne", "Italie", "Espagne"])
        finally:
            srv.close()


class PasteCircuitBreaker(unittest.TestCase):
    def setUp(self):
        setup_args()
        s.ARGS.threads = 1
        self.orig = (s.scrape_paste, s.time.sleep)
        s.time.sleep = lambda *a: None
        self.calls = []

    def tearDown(self):
        s.scrape_paste, s.time.sleep = self.orig

    def run_batch(self, cands, behaviour):
        def fake(url, title="", extra=None):
            self.calls.append(url)
            return behaviour(url)
        s.scrape_paste = fake
        return s.fetch_pastes([(u, "t", {}) for u in cands])

    def blocked(self):
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, None)

    def test_blocked_site_is_dropped_after_three_failures_other_sites_unaffected(self):
        def behaviour(url):
            if "bloque.example" in url:
                self.blocked()
            return {"url": url, "size": 1}
        cands = [f"https://bloque.example/{i}" for i in range(8)] + ["https://ok.example/1", "https://ok.example/2"]
        res = self.run_batch(cands, behaviour)
        self.assertEqual(sum("bloque.example" in c for c in self.calls), s.PASTE_MAX_FAILS)      # 3 essais puis on arrête
        self.assertEqual(len(res), 2)                                                              # l'autre site est lu normalement

    def test_expired_pastes_do_not_trip_the_breaker(self):
        def behaviour(url):
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        self.run_batch([f"https://vieux.example/{i}" for i in range(8)], behaviour)
        self.assertEqual(len(self.calls), 8)                                                       # 404 = expiré : on continue

    def test_a_success_resets_the_counter(self):
        seq = iter([False, False, True, False, False, True, False, False])
        def behaviour(url):
            if not next(seq):
                self.blocked()
            return {"url": url, "size": 1}
        self.run_batch([f"https://irregulier.example/{i}" for i in range(8)], behaviour)
        self.assertEqual(len(self.calls), 8)                                                       # jamais 3 échecs d'affilée


class Banner(unittest.TestCase):
    """La bannière ASCII doit épeler SCRAPAUD (8 lettres) : une version précédente dessinait « SCRAPUD » (un « A » manquant)."""

    GOLDEN = (
        "   ____   ____ ____      _    ____   _   _   _ ____\n"
        "  / ___| / ___|  _ \\    / \\  |  _ \\ / \\ | | | |  _ \\\n"
        "  \\___ \\| |   | |_) |  / _ \\ | |_) / _ \\| | | | | | |\n"
        "   ___) | |___|  _ <  / ___ \\|  __/ ___ \\ |_| | |_| |\n"
        "  |____/ \\____|_| \\_\\/_/   \\_\\_| /_/   \\_\\___/|____/"
    )

    def test_banner_spells_scrapaud(self):
        self.assertEqual(s.BANNER.strip("\n"), self.GOLDEN)

    def test_banner_has_eight_letters(self):
        # chaque lettre figlet « standard » a un motif de tête distinct : on compte les 2 « A » (pointe « / \\ » en 2e ligne)
        second = s.BANNER.strip("\n").splitlines()[1]
        self.assertEqual(second.count("/ \\"), 2)                                # deux « A » : S C R A P A U D

    def test_banner_fits_a_standard_terminal_and_is_ascii(self):
        rows = s.BANNER.strip("\n").splitlines()
        self.assertEqual(len(rows), 5)
        self.assertLessEqual(max(map(len, rows)), 80)
        self.assertTrue(all(ord(c) < 128 for c in s.BANNER))

    def test_banner_is_printed_by_the_cli(self):
        r = os_run([sys.executable, SCRIPT, "--help"])                            # l'aide n'affiche pas la bannière
        self.assertNotIn("____", r.stdout.split("options:")[0].split("usage:")[0])
        import subprocess
        out = subprocess.run([sys.executable, SCRIPT, "--doctor", "--no-color"], capture_output=True, text=True, timeout=60).stdout
        self.assertIn("scrapaud", out)


SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrapaud.py")


def os_run(cmd):
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
