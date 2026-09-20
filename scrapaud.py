#!/usr/bin/env python3
"""scrapaud - scraper de listes, liens et données pour n'importe quel sujet.

Recherche multi-moteurs (Bing, DuckDuckGo, Wikipedia, GitHub, HackerNews,
Archive.org) sur n'importe quel nom / mot-clé / chose, puis scraping des pages
(liens, listes, tableaux, images, emails, titres, texte) avec crawl optionnel.

Exemples :
  scrapaud.py -q "raspberry pi"                       # recherche (moteur auto)
  scrapaud.py -q "raspberry pi" -e all -p 2           # tous les moteurs, 2 pages
  scrapaud.py -q "raspberry pi" --searx http://127.0.0.1:8888   # via ton SearXNG (ou export SCRAPAUD_SEARX=...)
  scrapaud.py -q "linux distro" --follow -x links,items,emails
  scrapaud.py -q "rapport annuel" --filetype pdf --site gouv.fr
  scrapaud.py -u https://exemple.com --depth 2 --same-domain -o site.json
  scrapaud.py -Q sujets.txt --urls-only > urls.txt    # une recherche par ligne

Interface de sélection (-i) : cocher ce qu'on garde avant d'aller plus loin :
  scrapaud.py -q "sujet" -i                          # coche les résultats de recherche (espace, / filtre, Entrée)
  scrapaud.py -q "liste de mots" --textlist -i       # coche les sources, puis décoche le bruit dans les entrées
  scrapaud.py -u https://exemple.com --depth 1 -i    # coche les liens trouvés
  scrapaud.py -q "sujet" -i --urls-only > choix.txt  # l'interface s'affiche sur le terminal, le résultat va dans le fichier
  scrapaud.py -q "sujet" -i --plain                  # sans curses : liste numérotée (saisir 1,3-5 · a · n · /mot)

Diagnostic :
  scrapaud.py --doctor                                # état de l'installation (hors ligne, instantané)
  scrapaud.py --doctor --deep                         # + Internet, Tor réel, SearXNG, rendu JS, sondage de chaque moteur

Contenu principal des pages (sans menus / pieds de page / bandeaux) :
  scrapaud.py -u https://exemple.com/article --main -x text,links   # actif par défaut avec --wordlist (--no-main pour l'annuler)

Sécurité (par défaut) : cookies/-H limités aux hôtes ciblés, réseau privé bloqué, pause par site :
  scrapaud.py -u https://site.com --cookie "sid=..."           # le cookie ne part QUE vers site.com (jamais aux moteurs, retiré si redirection ailleurs)
  scrapaud.py -u https://a.com --cookie "x" --cookie-domain a.com --cookie-domain api.a.com
  scrapaud.py -q "sujet" --follow --allow-private              # autoriser 127.x / 10.x / 192.168.x / 169.254.x / Tailscale trouvés dans les résultats
  scrapaud.py -u http://192.168.1.1/ --allow-host nas.lan      # tes cibles explicites (-u/-f) et ton SearXNG sont déjà autorisés

Enregistrer les pastes lus dans des fichiers (un .txt par paste, classés par site et par date, + index.md) :
  scrapaud.py --pastebin --grep "mot" --paste-dir            # -> ~/pastes/scrapaud/pastebin-com/AAAAMMJJ/<id>_<titre>.txt
  scrapaud.py -q "sujet" --pastes --paste-dir ~/mes-pastes   # dossier au choix (droits 700, fichiers 600)

Wordlists .txt automatiques + vue en temps réel :
  scrapaud.py --wordlist -q "cybersécurité"           # cherche, lit les résultats, écrit ~/wordlists/scrapaud/<sujet>_<date>/wordlist.txt
  scrapaud.py --wordlist -u https://site.com --depth 2 --wl-lower --wl-min 4
  scrapaud.py --wordlist -u liste.txt -u https://exemple.com/mots.txt -o mots.txt
  scrapaud.py --wordlist -q "recettes" --wl-split -i  # un .txt par source + tri manuel avant écriture
  (tableau de bord live sur stderr : sources, mots uniques, débit, derniers mots, top ; --no-live pour le couper)

Catégories, documents, sitemaps, flux :
  scrapaud.py -q "chat" --category images --since week      # via SearXNG : images news videos science files it social
  scrapaud.py -q "post-quantum" --category science            # sans SearXNG : arXiv + OpenAlex
  scrapaud.py -q "rapport annuel" --filetype pdf --follow      # les PDF/docx/xlsx/pptx/odt sont lus (texte, liens, emails)
  scrapaud.py --sitemap -u https://exemple.com --urls-only     # toutes les URLs du sitemap (robots.txt, index récursifs)
  scrapaud.py -u https://exemple.com/feed.xml                  # RSS/Atom détecté automatiquement (aussi feeds d'une page)

Deep web / Tor (.onion) et bases publiques non indexées :
  scrapaud.py --onion -q "wiki"                      # recherche d'onions (Ahmia) ; les .onion sont lus via Tor
  scrapaud.py -u http://xxxx.onion --textlist        # tout .onion passe automatiquement par Tor (127.0.0.1:9050)
  scrapaud.py -q "exemple.com" -e crtsh,wayback      # sous-domaines (certificats) + pages archivées
  scrapaud.py -q "erreur nginx 502" -e stackexchange,gitlab
  scrapaud.py --tor -q "sujet"                       # TOUT le trafic via Tor

Listes de texte (wordlists, IP, domaines, emails... une entrée par ligne) :
  scrapaud.py --textlist -u https://exemple.com/liste.txt -o liste.txt
  scrapaud.py --textlist -u https://github.com/user/repo/blob/main/mots.txt --as domains --sort
  scrapaud.py --textlist -q "liste de mots" --min-len 4         # cherche puis extrait les listes des résultats
  cat notes.txt | scrapaud.py --textlist -u - --as emails        # stdin ou fichier local (-u chemin)

Pastes (sites publics de type pastebin) :
  scrapaud.py -q "mon-domaine.fr" --pastes           # cherche le sujet sur tous les sites de paste
  scrapaud.py --pastebin --grep "api[_-]?key"        # scanne les derniers pastes publics de pastebin.com
  scrapaud.py --pastebin --archive-syntax all -q leak --watch 300 -o pastes.json
  scrapaud.py --gists -q "token" --gist-pages 3      # derniers gists publics GitHub filtrés
  scrapaud.py -u https://pastebin.com/AbCdEfGh       # une URL de paste est lue en brut automatiquement
"""
import argparse
import base64
import atexit
import collections
import contextlib
import csv
import datetime
import glob
import gzip
import hashlib
import html as ihtml
import http.client
import ipaddress
import json
import os
import random
import re
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import zipfile
import zlib
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

try:
    import curses
except ImportError:      # pas de curses (Windows) : mode texte
    curses = None

VERSION = "3.8"

BANNER = r"""
   ____   ____ ____      _    ____   _   _   _ ____
  / ___| / ___|  _ \    / \  |  _ \ / \ | | | |  _ \
  \___ \| |   | |_) |  / _ \ | |_) / _ \| | | | | | |
   ___) | |___|  _ <  / ___ \|  __/ ___ \ |_| | |_| |
  |____/ \____|_| \_\/_/   \_\_| /_/   \_\___/|____/
"""

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
EXTRACTS = ("links", "items", "tables", "images", "emails", "headings", "text")

_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
_lock = threading.Lock()


def green(s):
    return f"\033[92m{s}\033[0m" if _color else str(s)


def dgreen(s):
    return f"\033[32m{s}\033[0m" if _color else str(s)


LIVE = [None]     # vue temps réel active (voir LiveView) : elle récupère les messages d'info()


def info(msg):
    """Messages de progression -> stderr, pour garder stdout pipeable."""
    if not ARGS.quiet:
        live = LIVE[0]
        if live is not None and live.active:
            live.log(msg)
            return
        with _lock:
            print(msg, file=sys.stderr)


def print_banner():
    if ARGS.quiet or ARGS.urls_only or ARGS.json or ((ARGS.textlist or ARGS.wordlist) and not sys.stdout.isatty()):
        return
    print(green(BANNER) + dgreen(f"  scrapaud v{VERSION} - scraper de listes, liens & données\n"))


# --------------------------------------------------------------------- HTTP
_opener = None


def build_opener(proxy):
    """Client HTTP : connexions filtrées (pas de réseau privé), redirections à portée limitée.
    Avec --proxy la connexion va au proxy choisi (le filtre ne peut plus voir la destination)."""
    class HTTPH(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(_GuardedHTTPConn, req)

    class HTTPSH(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(_GuardedHTTPSConn, req, context=self._context)
    class ProxyDestinationGuard(urllib.request.BaseHandler):
        """Avec --proxy la connexion part vers le proxy : on ne voit plus la destination. Contrôle préalable (à chaque saut,
        redirections comprises) : IP littérale privée ou nom qui RÉSOUT localement en adresse privée -> refusé."""
        handler_order = 50

        def _check(self, req):
            h = (urllib.parse.urlsplit(req.full_url).hostname or "").lower()      # gère [::1] avec ou sans port
            if ARGS.allow_private or host_trusted(h):
                return req
            if is_local_host(h):
                raise urllib.error.URLError(f"adresse privée bloquée : {h} (--allow-private ou --allow-host {h})")
            try:
                addrs = {i[4][0] for i in socket.getaddrinfo(h, None)}
            except OSError:
                return req                          # non résolvable ici : le proxy résoudra (on ne peut pas vérifier)
            if addrs and all(is_blocked_ip(a) for a in addrs):
                raise urllib.error.URLError(f"adresse privée bloquée : {h} → {sorted(addrs)[0]} (--allow-private ou --allow-host {h})")
            return req
        http_request = https_request = _check
    if proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                                           ProxyDestinationGuard(), _ScopedRedirect())
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), HTTPH(), HTTPSH(), _ScopedRedirect())


# ------------------------------------------------ sécurité : portée, réseau privé, politesse
def hostname(url):
    return (urllib.parse.urlparse(url).hostname or "").lower()


def _host_match(h, domains):
    return any(h == d or h.endswith("." + d) for d in domains)


def in_scope(url):
    """--cookie / -H ne partent que vers les hôtes ciblés (-u/-f ou --cookie-domain), jamais ailleurs."""
    return _host_match(hostname(url), ARGS._scope)


def host_trusted(h):
    """Hôtes explicitement demandés (-u/-f, --searx, --allow-host) : autorisés même sur réseau privé."""
    return _host_match(h.lower(), ARGS._trusted)


def is_blocked_ip(addr):
    """Vrai pour toute adresse non publique : privée, loopback, link-local (métadonnées cloud), CGNAT/Tailscale, réservée."""
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return True
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return not ip.is_global


def guarded_connect(host, port, timeout):
    """Connexion TCP qui refuse le réseau privé (SSRF, redirections, DNS rebinding) sauf hôte de confiance / --allow-private.
    On résout une seule fois et on se connecte à l'IP vérifiée."""
    if ARGS.allow_private or host_trusted(host):
        return socket.create_connection((host, port), timeout=timeout)
    last = None
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    public = [i for i in infos if not is_blocked_ip(i[4][0])]
    if not public:
        raise OSError(f"adresse privée bloquée : {host} → {infos[0][4][0]} (--allow-private ou --allow-host {host} pour l'autoriser)")
    for family, stype, proto, _, sa in public:
        sock = socket.socket(family, stype, proto)
        sock.settimeout(timeout)
        try:
            sock.connect(sa)
            return sock
        except OSError as e:
            last = e
            sock.close()
    raise last


class _GuardedHTTPConn(http.client.HTTPConnection):
    def connect(self):
        self.sock = guarded_connect(self.host, self.port, self.timeout)


class _GuardedHTTPSConn(http.client.HTTPSConnection):
    def connect(self):
        sock = guarded_connect(self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _ScopedRedirect(urllib.request.HTTPRedirectHandler):
    """Sur redirection vers un hôte hors portée, on retire cookie, Authorization et en-têtes perso."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not in_scope(newurl):
            for name in ("Cookie", "Authorization", "Proxy-authorization",
                         *[hd.partition(":")[0].strip().capitalize() for hd in ARGS.header]):
                new.remove_header(name)
        return new


_next_ok = {}
_thr_lock = threading.Lock()


def throttle(h):
    """Pause POLIE PAR HÔTE : deux requêtes vers le même site sont espacées d'au moins --delay, même avec plusieurs threads."""
    if ARGS.delay <= 0:
        return
    with _thr_lock:
        now = time.monotonic()
        at = max(now, _next_ok.get(h, 0.0))
        _next_ok[h] = at + ARGS.delay
    if at > now:
        time.sleep(at - now)


def setup_security(urls):
    """Calcule la portée des cookies et la liste des hôtes de confiance à partir des cibles demandées."""
    targets = {hostname(u) for u in urls if "://" in u}
    ARGS._explicit = {u.split("#")[0] for u in urls}
    ARGS._trusted |= targets
    if ARGS.searx:
        ARGS._trusted.add(hostname(ARGS.searx))      # ton SearXNG local reste joignable
    if ARGS.cookie or ARGS.header:
        ARGS._scope = {d.lower() for d in ARGS.cookie_domain} or set(targets)
        if not ARGS._scope:
            info("[!] --cookie/-H ignorés : aucune URL cible (-u/-f) ni --cookie-domain (jamais envoyés aux moteurs de recherche)")
        elif ARGS.render:
            info("[!] --cookie/-H ne sont PAS transmis au rendu JavaScript (--render) : la page sera vue sans session")
        elif any(u.lower().startswith("http://") and hostname(u) in ARGS._scope for u in urls):
            info("[!] --cookie/-H envoyés en clair (http://) : n'utilise ça que sur un réseau de confiance")

# --- Tor : client SOCKS5 minimal (DNS résolu côté Tor, aucune fuite locale)
def _recvn(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise OSError("SOCKS5 : connexion fermée")
        buf += chunk
    return buf


SOCKS_ERR = {1: "erreur générale", 2: "refusé", 3: "réseau injoignable", 4: "hôte injoignable",
             5: "connexion refusée", 6: "TTL expiré", 7: "commande non gérée", 8: "adresse non gérée"}


def socks5_connect(proxy, host, port, timeout):
    if not (ARGS.allow_private or host_trusted(host)) and is_local_host(host.lower()):
        raise OSError(f"adresse privée bloquée : {host} (via Tor aussi ; --allow-private ou --allow-host {host} pour l'autoriser)")
    sock = socket.create_connection(proxy, timeout=timeout)
    try:
        sock.sendall(b"\x05\x01\x00")
        if _recvn(sock, 2) != b"\x05\x00":
            raise OSError("SOCKS5 : méthode d'authentification refusée")
        hb = host.encode("idna")
        sock.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + struct.pack(">H", port))
        head = _recvn(sock, 4)
        if head[1] != 0:
            raise OSError(f"SOCKS5 : {SOCKS_ERR.get(head[1], head[1])} ({host})")
        if head[3] == 1:
            _recvn(sock, 4)
        elif head[3] == 4:
            _recvn(sock, 16)
        else:
            _recvn(sock, _recvn(sock, 1)[0])
        _recvn(sock, 2)
        return sock
    except Exception:
        sock.close()
        raise


class _SocksHTTPConn(http.client.HTTPConnection):
    _proxy = None

    def connect(self):
        self.sock = socks5_connect(self._proxy, self.host, self.port, self.timeout)


class _SocksHTTPSConn(http.client.HTTPSConnection):
    _proxy = None

    def connect(self):
        sock = socks5_connect(self._proxy, self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _mk(cls, host, proxy, **kw):
    c = cls(host, **kw)
    c._proxy = proxy
    return c


_tor = None


def is_onion(url):
    h = urllib.parse.urlparse(url).hostname or ""
    return h.endswith(".onion")


def tor_opener():
    global _tor
    if _tor is None:
        ph, _, pp = (ARGS.tor_proxy or "127.0.0.1:9050").rpartition(":")
        proxy = (ph or "127.0.0.1", int(pp))
        try:
            socket.create_connection(proxy, timeout=2).close()
        except OSError:
            raise ValueError(f"Tor injoignable sur {proxy[0]}:{proxy[1]} (systemctl status tor, ou --tor-proxy hôte:port)")

        class HTTPH(urllib.request.HTTPHandler):
            def http_open(self, req):
                return self.do_open(lambda host, **kw: _mk(_SocksHTTPConn, host, proxy, **kw), req)

        class HTTPSH(urllib.request.HTTPSHandler):
            def https_open(self, req):
                return self.do_open(lambda host, **kw: _mk(_SocksHTTPSConn, host, proxy, **kw), req,
                                    context=self._context)

        _tor = urllib.request.build_opener(urllib.request.ProxyHandler({}), HTTPH(), HTTPSH(), _ScopedRedirect())
    return _tor


_direct = None


def is_local_host(h):
    """localhost ou adresse littérale privée/loopback : ne doit jamais passer par un proxy externe."""
    if h == "localhost" or h.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(h.split("%")[0])
    except ValueError:
        return False                       # un nom de domaine n'est pas « local » (is_blocked_ip traiterait le texte comme suspect)
    return is_blocked_ip(h)


def pick_opener(url):
    """Tor pour les .onion (toujours) et pour tout le trafic avec --tor ; le proxy (--proxy) sauf pour le trafic local
    (ton SearXNG sur 127.0.0.1 reste en direct) ; sinon l'opener normal."""
    global _direct
    if ARGS.tor or is_onion(url):
        return tor_opener()
    if ARGS.proxy and is_local_host(hostname(url)):
        if _direct is None:
            _direct = build_opener(None)
        return _direct
    return _opener


DOC_MAX = 30_000_000      # taille max d'un document binaire téléchargé
UNZIP_MAX = 50_000_000    # borne anti "bombe de décompression"


def _inflate(raw, wbits):
    out = zlib.decompressobj(wbits).decompress(raw, UNZIP_MAX)
    return out


def fetch(url, data=None, headers=None, retries=None, want_json=False, binary=False, max_bytes=None):
    """GET/POST avec retries, gzip/deflate, limite de taille. -> (texte, url_finale, content_type)."""
    retries = ARGS.retries if retries is None else retries
    opener = pick_opener(url)
    timeout = max(ARGS.timeout, 45) if opener is _tor else ARGS.timeout       # Tor est lent
    last = None
    for attempt in range(retries + 1):
        wait = None
        h = {
            "User-Agent": ARGS.user_agent or random.choice(USER_AGENTS),
            "Accept": "application/json" if want_json else "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": f"{ARGS.lang},en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
        }
        if in_scope(url):   # jamais vers les moteurs de recherche ni un autre domaine
            if ARGS.cookie:
                h["Cookie"] = ARGS.cookie
            for hd in ARGS.header:
                k, _, v = hd.partition(":")
                h[k.strip()] = v.strip()
        h.update(headers or {})
        try:
            throttle(hostname(url))
            req = urllib.request.Request(url, data=data, headers=h)
            with opener.open(req, timeout=timeout) as r:
                raw = r.read(max_bytes or ARGS.max_bytes)
                enc = (r.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = _inflate(raw, 31)
                elif enc == "deflate":
                    raw = _inflate(raw, zlib.MAX_WBITS)
                ctype = r.headers.get("Content-Type", "")
                if binary:
                    return raw, r.geturl(), ctype
                cs = r.headers.get_content_charset() or "utf-8"
                return raw.decode(cs, errors="replace"), r.geturl(), ctype
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                break
            ra = e.headers.get("Retry-After") if e.headers else None
            if ra and ra.isdigit():
                wait = min(int(ra), 30)   # respecte le serveur (plafonné)
        except Exception as e:  # réseau, timeout, décompression...
            last = e
        if attempt < retries:
            time.sleep(wait if wait else min(2 ** attempt, 8) * (0.5 + random.random()))
    if ARGS.proxy and isinstance(last, urllib.error.URLError) and not isinstance(last, urllib.error.HTTPError) \
            and not is_local_host(hostname(url)):
        raise urllib.error.URLError(f"{last.reason} (via --proxy {ARGS.proxy} : proxy injoignable ou refusé ?)") from last
    raise last


# --------------------------------------------------------------------- cache
CACHE_DIR = os.path.expanduser(os.environ.get("SCRAPAUD_CACHE", "~/.cache/scrapaud"))
CACHE_MAX = 32 * 1024 * 1024      # disque du home quasi plein : cache volontairement petit
CACHE_ENTRY_MAX = 2 * 1024 * 1024
_cache_puts = [0]


def cache_key(*parts):
    return hashlib.sha256("\x00".join(map(str, parts)).encode("utf-8")).hexdigest()


def cache_get(key):
    if ARGS.no_cache or ARGS.cache_ttl <= 0:
        return None
    path = os.path.join(CACHE_DIR, key + ".json.gz")
    try:
        if time.time() - os.path.getmtime(path) > ARGS.cache_ttl:
            return None
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, EOFError):
        return None


def cache_put(key, obj):
    if ARGS.no_cache or ARGS.cache_ttl <= 0:
        return
    try:
        data = gzip.compress(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        if len(data) > CACHE_ENTRY_MAX:
            return
        os.makedirs(CACHE_DIR, mode=0o700, exist_ok=True)
        path = os.path.join(CACHE_DIR, key + ".json.gz")
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        _cache_puts[0] += 1
        if _cache_puts[0] % 20 == 0:
            cache_trim()
    except OSError:
        pass


def cache_trim(limit=None):
    """Supprime les entrées les plus anciennes au-delà de CACHE_MAX (retombe à 75 %)."""
    limit = CACHE_MAX if limit is None else limit
    files = []
    for p in glob.glob(os.path.join(CACHE_DIR, "*.json.gz")):
        try:
            st = os.stat(p)
            files.append((st.st_mtime, st.st_size, p))
        except OSError:
            pass
    total = sum(sz for _, sz, _ in files)
    if total <= limit:
        return 0
    removed = 0
    for _, sz, p in sorted(files):
        if total <= limit * 0.75:
            break
        try:
            os.remove(p)
            total -= sz
            removed += 1
        except OSError:
            pass
    return removed


def cache_clear():
    n = 0
    for p in glob.glob(os.path.join(CACHE_DIR, "*.json.gz")):
        try:
            os.remove(p)
            n += 1
        except OSError:
            pass
    return n


def fetch_c(url, **kw):
    """fetch() avec cache disque (pages, pastes, sitemaps). Jamais pour le binaire ni les moteurs de recherche."""
    if (ARGS.cookie or ARGS.header) and in_scope(url):
        return fetch(url, **kw)      # requête authentifiée : ni lue ni écrite dans le cache (contenu privé, resservi sans cookie sinon)
    key = cache_key("page", url, ARGS.render)
    hit = cache_get(key)
    if hit:
        return tuple(hit)
    res = fetch(url, **kw)
    cache_put(key, list(res))
    return res


_robots = {}


def robots_applies(url):
    """--robots / --no-robots forcent ; par défaut (auto) : robots.txt respecté pour ce qui est DÉCOUVERT (liens suivis,
    résultats de recherche, sitemaps), pas pour les URLs que l'utilisateur a tapées lui-même (-u / -f)."""
    if ARGS.robots is not None:
        return ARGS.robots
    return url.split("#")[0] not in ARGS._explicit


def allowed_by_robots(url):
    if not robots_applies(url):
        return True
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    rp = _robots.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            txt, _, _ = fetch(base + "/robots.txt", retries=0)
            rp.parse(txt.splitlines())
        except Exception:
            rp.parse([])
        _robots[base] = rp
    return rp.can_fetch("*", url)


# ------------------------------------------------------------------- parsing
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
UI_RE = re.compile(r"nav|menu|lang|dropdown|sidebar|toc|footer|header|breadcrumb|pagination|cookie|banner", re.I)


MAX_DEPTH = 200        # profondeur d'imbrication suivie : au-delà, les balises sont ignorées (page hostile = coût quadratique sinon)
MAX_LIST_DEPTH = 64

MAIN_RE = re.compile(r"(?:^|[\s_-])(article|post|entry|story|content|main|texte|prose)(?:$|[\s_-])", re.I)
BOILER_RE = re.compile(r"cookies?\b|accepter|tout refuser|newsletter|abonn(?:ez|ement)|s.abonner|mentions l[ée]gales|"
                       r"politique de confidentialit|tous droits r[ée]serv|all rights reserved|©|se connecter|sign in|log in|"
                       r"cr[ée]er un compte|partager|suivez.nous|follow us|share this|skip to|aller au contenu|retour en haut", re.I)


class PageParser(HTMLParser):
    """Extrait titre, description, liens, li/tr, tableaux, images, titres, texte."""

    SKIP = ("script", "style", "noscript", "template")

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title = ""
        self.description = ""
        self.links, self.items, self.images, self.headings = [], [], [], []
        self.tables = []
        self.text = []
        self._a = None
        self._li = None
        self._skip = 0
        self._in_title = False
        self._h = None
        self._table = None
        self._row = None
        self._cell = None
        self.pre = []
        self._pre = None
        self.table_headers = []   # par tableau : une liste de booléens « ligne d'en-tête (que des <th>) »
        self._table_hdr = None
        self._row_th = None
        self._cell_th = False
        self.lists = []      # (dans_main, [textes]) par <ul>/<ol> (pour choisir la plus grande)
        self._lstack = []
        self.feeds = []
        self._stk = []       # éléments ouverts : (tag, est_interface, est_contenu) pour ignorer menus / sélecteurs de langue
        self._para = 0       # dans un <p>/<blockquote>
        self.pieces = []     # (texte, interface, contenu, dans_un_lien, dans_un_paragraphe)
        self.links_main = []
        self.items_main = []

    def _abs(self, u):
        return urllib.parse.urljoin(self.base, u.strip())

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in VOID_TAGS and len(self._stk) < MAX_DEPTH:
            # html/body portent des classes de mise en page (« vector-toc-pinned »…) : jamais un signal d'interface
            cid = "" if tag in ("html", "body") else (a.get("class") or "") + " " + (a.get("id") or "")
            mn = tag in ("main", "article") or a.get("role") == "main" or bool(MAIN_RE.search(cid))
            # balise sémantique (nav/header/footer/aside/form) = interface ; par classe seulement si ce n'est pas aussi du contenu
            ui = tag in ("nav", "header", "footer", "aside", "form") or (bool(UI_RE.search(cid)) and not mn)
            self._stk.append((tag, ui, mn))
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "link" and "alternate" in (a.get("rel") or "").lower() and \
                re.search(r"rss|atom", a.get("type") or "", re.I) and a.get("href"):
            self.feeds.append(self._abs(a["href"]))
        elif tag == "meta" and (a.get("name") or a.get("property") or "").lower() in ("description", "og:description"):
            self.description = self.description or (a.get("content") or "").strip()
        elif tag == "a" and a.get("href"):
            href = a["href"].strip()
            if not href.lower().startswith(("javascript:", "#", "mailto:", "tel:", "data:")):
                self._a = {"url": self._abs(href), "text": ""}
        elif tag == "img" and (a.get("src") or a.get("data-src")):
            self.images.append({"url": self._abs(a.get("src") or a.get("data-src")), "alt": (a.get("alt") or "").strip()})
        elif tag in ("h1", "h2", "h3", "h4"):
            self._h = ""
        elif tag in ("p", "blockquote"):
            self._para = 1
        elif tag in ("pre", "textarea"):
            self._pre = ""
        elif tag in ("ul", "ol") and len(self._lstack) < MAX_LIST_DEPTH:
            self._lstack.append(([], self._state()[0]))
        elif tag == "table":
            self._table = []
            self._table_hdr = []
        elif tag == "tr":
            self._row = []
            self._row_th = []
            self._li = ""
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ""
            self._cell_th = tag == "th"
        elif tag == "li":
            self._li = ""

    def handle_endtag(self, tag):
        for i in range(len(self._stk) - 1, -1, -1):
            if self._stk[i][0] == tag:
                del self._stk[i:]
                break
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._a:
            self._a["text"] = " ".join(self._a["text"].split())
            self.links.append(self._a)
            if not self._state()[0]:
                self.links_main.append(self._a)
            self._a = None
        elif tag in ("h1", "h2", "h3", "h4") and self._h is not None:
            t = " ".join(self._h.split())
            if t:
                self.headings.append({"level": int(tag[1]), "text": t})
            self._h = None
        elif tag in ("p", "blockquote"):
            self._para = 0
        elif tag in ("pre", "textarea") and self._pre is not None:
            self.pre.append(self._pre)
            self._pre = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join(self._cell.split()))
            self._row_th.append(self._cell_th)
            self._cell = None
        elif tag == "tr":
            if self._row and self._table is not None and any(self._row):
                self._table.append(self._row)
                self._table_hdr.append(bool(self._row_th) and all(self._row_th))
            self._row = None
            self._flush_li()
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
                self.table_headers.append(self._table_hdr)
            self._table = None
        elif tag == "li":
            self._flush_li(True)
        elif tag in ("ul", "ol") and self._lstack:
            items, is_ui = self._lstack.pop()
            self.lists.append((is_ui, items))

    def _flush_li(self, is_li=False):
        if self._li is not None:
            t = " ".join(self._li.split())
            if t:
                self.items.append(t)
                if not self._state()[0]:
                    self.items_main.append(t)
                if is_li and self._lstack:
                    self._lstack[-1][0].append(t)
            self._li = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._a is not None:
            self._a["text"] += data
        if self._h is not None:
            self._h += data
        if self._li is not None:
            self._li += data + " "
        if self._cell is not None:
            self._cell += data
        if self._pre is not None:
            self._pre += data
        if data.strip():
            self.text.append(data.strip())
            ui, in_main = self._state()
            self.pieces.append((data.strip(), ui, in_main, self._a is not None, self._para > 0))

    def _state(self):
        """(interface, contenu_principal) à l'endroit courant : l'élément le plus profond décide.
        Une zone d'interface DANS un article reste de l'interface ; un article DANS un conteneur de mise en page « sidebar » reste du contenu."""
        ui = None
        in_main = False
        for _tag, u, m in reversed(self._stk):
            if ui is None and u:
                ui = True
            if m:
                in_main = True
                if ui is None:
                    ui = False
        return bool(ui), in_main

    def main_pieces(self):
        """Texte du contenu principal : sans menus, en-têtes/pieds, formulaires, liens de navigation, bandeaux cookies."""
        body = [x for x in self.pieces if not x[1]]
        core = [x for x in body if x[2]]
        if sum(len(x[0]) for x in core) >= 200:          # zone « article/main » assez fournie : on s'y limite
            body = core
        out, prev = [], None
        for text, _ui, _mn, in_link, in_para in body:
            if in_link and not in_para and len(text) < 40:      # court texte de lien hors paragraphe = navigation
                continue
            if len(text) < 80 and BOILER_RE.search(text):
                continue
            if text != prev:
                out.append(text)
            prev = text
        return out


def best_column(tables, headers):
    """Colonne de tableau la plus « liste de noms » : valeurs uniques avec des lettres, courtes, hors lignes d'en-tête.
    (évite les colonnes de codes/nombres/drapeaux et les en-têtes) -> liste de valeurs, [] si rien de net."""
    best, best_score = [], 0
    for t, hd in zip(tables, headers):
        rows = [r for r, h in zip(t, hd) if not h]
        if len(rows) < 3:
            continue
        for c in range(max(len(r) for r in rows)):
            vals = [r[c].strip() for r in rows if c < len(r) and r[c].strip()]
            good = [v for v in vals if re.search(r"[^\W\d_]", v) and len(v) <= 60]
            score = len(set(good))
            if score > best_score and len(good) >= 0.6 * len(rows):
                best, best_score = good, score
    return best


def uniq(seq, key=None):
    seen, out = set(), []
    for x in seq:
        k = key(x) if key else x
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def host(url):
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def link_ok(l, page_url):
    u = l["url"]
    if not u.startswith(("http://", "https://")):
        return False
    if ARGS.same_domain and host(u) != host(page_url):
        return False
    if ARGS.external and host(u) == host(page_url):
        return False
    if ARGS.domain and not any(d in host(u) for d in ARGS.domain):
        return False
    if ARGS.not_domain and any(d in host(u) for d in ARGS.not_domain):
        return False
    if ARGS.ext:
        path = urllib.parse.urlparse(u).path.lower()
        if not path.endswith(tuple("." + e.lstrip(".").lower() for e in ARGS.ext)):
            return False
    return True


def text_ok(*parts):
    blob = " ".join(parts)
    if ARGS._grep and not ARGS._grep.search(blob):
        return False
    if ARGS._exclude and ARGS._exclude.search(blob):
        return False
    return True


# --------------------------------------------------------- rendu JavaScript
_render_lock = threading.Lock()   # un seul Chromium à la fois (RAM limitée)


def find_browser():
    if ARGS.browser:
        return ARGS.browser.split()
    for b in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        if shutil.which(b):
            return [b]
    if shutil.which("flatpak") and subprocess.run(["flatpak", "info", "org.chromium.Chromium"],
                                                    capture_output=True).returncode == 0:
        return ["flatpak", "run", "org.chromium.Chromium"]
    raise ValueError("--render : aucun Chromium/Chrome trouvé (utilise --browser \"commande\")")


class GuardProxy:
    """Proxy HTTP/CONNECT local (127.0.0.1, port éphémère) qui applique le filtre réseau privé.
    Chromium (--render) y passe TOUT son trafic : redirections, sous-ressources, fetch() de la page… (sinon il pourrait
    joindre 127.0.0.1 / le LAN / les métadonnées cloud tout seul). Via Tor : sortie SOCKS5 au lieu de la connexion directe."""

    def __init__(self, tor=False):
        self.tor = tor
        self.blocked = []
        self._lock = threading.Lock()
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(64)
        self.port = self.srv.getsockname()[1]
        self._closed = False
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        self._closed = True
        try:
            self.srv.close()
        except OSError:
            pass

    def _accept(self):
        while not self._closed:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(c,), daemon=True).start()

    def _open(self, host, port):
        try:
            if self.tor or host.endswith(".onion"):
                ph, _, pp = (ARGS.tor_proxy or "127.0.0.1:9050").rpartition(":")
                return socks5_connect((ph or "127.0.0.1", int(pp)), host, port, 45)
            return guarded_connect(host, port, 20)
        except OSError as e:
            if "bloquée" in str(e):
                with self._lock:
                    self.blocked.append(host)
            return None

    @staticmethod
    def _pipe(a, b):
        socks = [a, b]
        try:
            while True:
                r, _, _ = select.select(socks, [], [], 60)
                if not r:
                    return
                for x in r:
                    d = x.recv(65536)
                    if not d:
                        return
                    (b if x is a else a).sendall(d)
        except OSError:
            pass
        finally:
            for x in socks:
                try:
                    x.close()
                except OSError:
                    pass

    def _handle(self, c):
        up = None
        try:
            c.settimeout(30)
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 65536:
                d = c.recv(65536)
                if not d:
                    return
                buf += d
            head, _, rest = buf.partition(b"\r\n\r\n")
            lines = head.split(b"\r\n")
            method, target, _ver = lines[0].decode("latin-1").split(" ", 2)
            if method == "CONNECT":
                host, _, port = target.rpartition(":")
                up = self._open(host.strip("[]"), int(port or 443))
                if up is None:
                    c.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                    return
                c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                if rest:
                    up.sendall(rest)
            else:
                u = urllib.parse.urlparse(target)
                up = self._open(u.hostname or "", u.port or 80)
                if up is None:
                    c.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                    return
                path = (u.path or "/") + ("?" + u.query if u.query else "")
                hdr = [f"{method} {path} HTTP/1.1"] + [l.decode("latin-1") for l in lines[1:]
                                                       if not l.lower().startswith((b"proxy-", b"connection:", b"keep-alive"))]
                up.sendall(("\r\n".join(hdr + ["Connection: close"]) + "\r\n\r\n").encode("latin-1") + rest)
            c.settimeout(None)
            self._pipe(c, up)
            up = None
        except (OSError, ValueError):
            pass
        finally:
            for x in (up, c):
                try:
                    if x:
                        x.close()
                except OSError:
                    pass


def render_dom(url):
    """DOM d'une page après exécution du JavaScript (Chromium headless, profil jetable)."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("--render : uniquement des URLs http(s)")
    h = hostname(url)
    if not (ARGS.allow_private or host_trusted(h) or is_onion(url)):
        try:
            addrs = {i[4][0] for i in socket.getaddrinfo(h, None)}
        except OSError:
            addrs = set()
        if any(is_blocked_ip(a) for a in addrs):
            raise ValueError(f"--render : adresse privée bloquée ({h}) ; --allow-private ou --allow-host {h}")
    profile = os.path.join(tempfile.gettempdir(), f"scrapaud-chrome-{os.getpid()}")
    cmd = find_browser() + ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                            "--disable-extensions", "--mute-audio", f"--user-data-dir={profile}",
                            f"--virtual-time-budget={int(ARGS.render_wait * 1000)}", "--dump-dom"]
    cmd.append("--force-webrtc-ip-handling-policy=disable_non_proxied_udp")
    guard = None
    if ARGS.proxy and not (ARGS.tor or is_onion(url)):
        cmd.append(f"--proxy-server={ARGS.proxy}")       # proxy amont choisi par l'utilisateur : le filtre ne peut pas s'y appliquer
        info("[!] --render avec --proxy : le filtre réseau privé n'est pas appliqué au trafic de Chromium")
    else:
        guard = GuardProxy(tor=ARGS.tor or is_onion(url))
        cmd += [f"--proxy-server=http://127.0.0.1:{guard.port}", "--proxy-bypass-list=<-loopback>"]   # loopback aussi via le filtre
    if ARGS.user_agent:
        cmd.append(f"--user-agent={ARGS.user_agent}")
    cmd.append(url)
    try:
        with _render_lock:
            r = subprocess.run(cmd, capture_output=True, timeout=ARGS.render_timeout)
    except subprocess.TimeoutExpired:
        raise ValueError(f"--render : délai dépassé ({ARGS.render_timeout}s)")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        if guard:
            guard.close()
            if guard.blocked:
                info(f"[!] --render : connexions privées bloquées : {', '.join(sorted(set(guard.blocked)))}")
    out = r.stdout.decode("utf-8", errors="replace")
    if not out.strip():
        raise ValueError("--render : rendu vide (" + r.stderr.decode("utf-8", errors="replace").strip()[-160:] + ")")
    return out


def render_or_fetch(url):
    if ARGS.render:
        key = cache_key("page", url, True)
        hit = cache_get(key)
        if hit:
            return tuple(hit)
        res = (render_dom(url), url, "text/html")
        cache_put(key, list(res))
        return res
    return fetch_c(url)


# ----------------------------------------------- documents, sitemaps, flux RSS
DOC_EXT = (".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp")
DOC_CTYPES = (("pdf", "pdf"), ("wordprocessingml", "docx"), ("spreadsheetml", "xlsx"), ("presentationml", "pptx"),
              ("opendocument.text", "odt"), ("opendocument.spreadsheet", "ods"), ("opendocument.presentation", "odp"))
XML_ROOT_RE = re.compile(r"\s*(?:<\?xml[^>]*>\s*)?(?:<!--.*?-->\s*)*<(urlset|sitemapindex|rss|feed|rdf:RDF)\b", re.S | re.I)


def doc_kind(url):
    path = urllib.parse.urlparse(url).path.lower()
    return next((e[1:] for e in DOC_EXT if path.endswith(e)), None)


def sniff_doc_kind(body, ctype):
    """Type de document d'après le content-type ou la signature (%PDF)."""
    if body.startswith("%PDF-"):
        return "pdf"
    ct = ctype.lower()
    return next((k for pat, k in DOC_CTYPES if pat in ct), None)


def _zip_member(z, name):
    info_ = z.getinfo(name)
    if info_.file_size > UNZIP_MAX:
        raise ValueError(f"{name} trop volumineux dans l'archive")
    return z.read(name).decode("utf-8", errors="replace")


def _xml_text(xml, para_end, tab=None):
    xml = re.sub(para_end, "\n", xml)
    if tab:
        xml = re.sub(tab, "\t", xml)
    return ihtml.unescape(re.sub(r"<[^>]+>", "", xml))


def extract_doc_text(data, kind):
    """Texte d'un PDF (pdftotext) ou d'un document Office/OpenDocument (zip+XML, sans dépendance)."""
    if kind == "pdf":
        try:
            r = subprocess.run(["pdftotext", "-q", "-enc", "UTF-8", "-", "-"], input=data, capture_output=True, timeout=90)
        except FileNotFoundError:
            raise ValueError("lecture PDF : installe poppler-utils (pdftotext)")
        except subprocess.TimeoutExpired:
            raise ValueError("lecture PDF : délai dépassé")
        if r.returncode != 0:
            raise ValueError("PDF illisible (chiffré ou corrompu)")
        return r.stdout.decode("utf-8", errors="replace")
    import io
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError(f"fichier {kind} illisible")
    names = z.namelist()
    if kind == "docx":
        return _xml_text(_zip_member(z, "word/document.xml"), r"</w:p>", r"<w:tab/>")
    if kind == "xlsx":
        if "xl/sharedStrings.xml" not in names:
            return ""
        return _xml_text(_zip_member(z, "xl/sharedStrings.xml"), r"</si>")
    if kind == "pptx":
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.findall(r"\d+", n)[0]))
        return "\n".join(_xml_text(_zip_member(z, n), r"</a:p>") for n in slides)
    if kind in ("odt", "ods", "odp"):
        return _xml_text(_zip_member(z, "content.xml"), r"</text:(?:p|h)>|</table:table-row>")
    return ""


def scrape_document(url, kind, data=None, final=None):
    if data is None:
        data, final, _ = fetch(url, binary=True, max_bytes=DOC_MAX)
    final = final or url
    text = extract_doc_text(data, kind)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    want = ARGS._extract
    page = {"url": final, "type": "document", "doctype": kind,
            "title": os.path.basename(urllib.parse.urlparse(final).path) or final,
            "description": f"{len(data)} o, {len(lines)} lignes de texte"}
    if "links" in want:
        page["links"] = [{"url": u.rstrip(".,;)"), "text": ""} for u in uniq(URL_RE.findall(text))
                         if link_ok({"url": u.rstrip(".,;)")}, final) and text_ok(u)]
    if "items" in want:
        page["items"] = [l for l in lines if text_ok(l)][: ARGS.max_items]
    if "emails" in want:
        page["emails"] = sorted(set(EMAIL_RE.findall(text)))
    if "text" in want:
        page["text"] = text[:20000]
    return page


def _loc_blocks(xml, tag):
    """[(loc, lastmod)] des blocs <url>/<sitemap> (regex : pas d'analyse XML donc pas d'entités externes)."""
    out = []
    for blk in re.findall(rf"<{tag}\b.*?</{tag}>", xml, re.S | re.I):
        loc = re.search(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", blk, re.S | re.I)
        mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", blk, re.S | re.I)
        if loc:
            out.append((ihtml.unescape(loc.group(1)), mod.group(1) if mod else ""))
    return out


def read_sitemap(url, depth=0, seen=None):
    """URLs d'un sitemap, index récursifs compris (2 niveaux), bornés par --sitemap-max."""
    seen = seen if seen is not None else set()
    if url in seen or len(seen) >= 200:
        return []
    seen.add(url)
    body, _, _ = fetch_c(url)
    urls = [{"url": u, "text": m} for u, m in _loc_blocks(body, "url")]
    if depth < 2:
        for sub, _m in _loc_blocks(body, "sitemap"):
            if len(urls) >= ARGS.sitemap_max:
                break
            try:
                urls += read_sitemap(sub, depth + 1, seen)
            except Exception as e:
                info(f"[!] sitemap {sub} : {e}")
    return urls[: ARGS.sitemap_max]


def discover_sitemaps(url):
    p = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    base = f"{p.scheme}://{p.netloc}"
    found = []
    try:
        robots, _, _ = fetch(base + "/robots.txt", retries=0)
        found += re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots)
    except Exception:
        pass
    return uniq(found + [base + "/sitemap.xml", base + "/sitemap_index.xml"])


def sitemap_page(url, direct=False):
    """Page-résultat listant les URLs d'un sitemap (URL directe, ou découverte via robots.txt)."""
    path = urllib.parse.urlparse(url).path.lower()
    cands = [url] if direct or path.endswith((".xml", ".xml.gz")) else discover_sitemaps(url)
    urls, used = [], None
    for c in cands:
        try:
            urls = read_sitemap(c)
        except Exception as e:
            info(dgreen(f"    {c} : {e}"))
            continue
        if urls:
            used = c
            break
    if not urls:
        raise ValueError("aucun sitemap trouvé")
    links = [l for l in urls if link_ok(l, used) and text_ok(l["url"])]
    return {"url": used, "type": "sitemap", "title": f"sitemap ({len(links)} URLs)", "description": "", "links": links}


def parse_feed(body, url):
    """RSS 2.0 / Atom / RDF -> page-résultat (entrées dans links + items)."""
    if "<!ENTITY" in body:
        raise ValueError("flux refusé (entités XML)")
    try:
        root = ET.fromstring(body.lstrip().encode("utf-8"))
    except ET.ParseError as e:
        raise ValueError(f"flux XML invalide : {e}")
    strip = lambda t: t.rsplit("}", 1)[-1]
    txt = lambda el, name: next(((c.text or "").strip() for c in el if strip(c.tag) == name), "")
    entries = []
    for el in root.iter():
        if strip(el.tag) in ("item", "entry"):
            link = txt(el, "link")
            if not link:  # Atom : <link href="..."/>
                for c in el:
                    if strip(c.tag) == "link" and c.get("href") and c.get("rel", "alternate") == "alternate":
                        link = c.get("href")
                        break
            entries.append({"title": clean(txt(el, "title")), "url": link,
                            "date": txt(el, "pubDate") or txt(el, "published") or txt(el, "updated") or txt(el, "date"),
                            "summary": clean(txt(el, "description") or txt(el, "summary"))[:300]})
    ftitle = next((clean(c.text) for c in root.iter() if strip(c.tag) == "title" and c.text), "")
    entries = [e for e in entries if text_ok(e["title"], e["url"], e["summary"])]
    page = {"url": url, "type": "feed", "title": ftitle or "flux", "description": f"{len(entries)} entrées", "entries": entries}
    if "links" in ARGS._extract:
        page["links"] = [{"url": e["url"], "text": e["title"]} for e in entries if e["url"]]
    if "items" in ARGS._extract:
        page["items"] = [f"{e['date'][:16]}  {e['title']}".strip() for e in entries]
    return page


def scrape_page(url):
    """Télécharge et analyse une page -> dict selon --extract."""
    if ARGS.sitemap:
        return sitemap_page(url)
    kind = doc_kind(url)
    if kind:
        return scrape_document(url, kind)
    body, final, ctype = render_or_fetch(url)
    kind = sniff_doc_kind(body, ctype)
    if kind:  # document sans extension dans l'URL : on retélécharge en binaire
        return scrape_document(url, kind)
    root = XML_ROOT_RE.match(body[:3000])
    if root:
        if root.group(1).lower() in ("urlset", "sitemapindex"):
            return sitemap_page(url, direct=True)
        return parse_feed(body, final)
    page = {"url": final, "title": "", "description": ""}
    want = ARGS._extract

    if "html" not in ctype.lower() and "xml" not in ctype.lower() and not body.lstrip().startswith("<"):
        # texte brut / liste : chaque ligne = un élément, + toutes les URLs trouvées
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        links = [{"url": u.rstrip(".,;"), "text": ""} for u in uniq(URL_RE.findall(body))]
        page["items"] = [l for l in lines if text_ok(l)][: ARGS.max_items]
        page["links"] = [l for l in links if text_ok(l["url"]) and link_ok(l, final)]
        if "emails" in want:
            page["emails"] = sorted(set(EMAIL_RE.findall(body)))
        return page

    p = PageParser(final)
    p.feed(body)
    page["title"] = " ".join(p.title.split())
    page["description"] = p.description
    if p.feeds:
        page["feeds"] = uniq(p.feeds)
    if not ARGS.render and not p.links and not p.items and body.lower().count("<script") >= 3:
        page["hint"] = "page quasi vide : elle semble construite en JavaScript, essaie --render"

    if "links" in want:
        links = uniq(p.links_main if ARGS.main else p.links, key=lambda l: l["url"])
        page["links"] = [l for l in links if link_ok(l, final) and text_ok(l["url"], l["text"])]
    if "items" in want:
        page["items"] = [i for i in uniq(p.items_main if ARGS.main else p.items) if text_ok(i)][: ARGS.max_items]
    if "tables" in want:
        page["tables"] = p.tables
    if "images" in want:
        page["images"] = [i for i in uniq(p.images, key=lambda i: i["url"]) if text_ok(i["url"], i["alt"])]
    if "headings" in want:
        page["headings"] = p.headings
    if "emails" in want:
        emails = set(EMAIL_RE.findall(ihtml.unescape(body)))
        page["emails"] = sorted(e for e in emails if not e.lower().endswith((".png", ".jpg", ".gif", ".webp", ".svg")))
    if "text" in want:
        page["text"] = " ".join(p.main_pieces() if ARGS.main else p.text)[:20000]
    page["_all_links"] = uniq([l["url"] for l in p.links if link_ok(l, final)])  # pour le crawl
    return page


def crawl(start_urls):
    """BFS multi-thread jusqu'à --depth / --max-pages."""
    seen, pages = set(), []
    level = uniq(start_urls)
    depth = 0
    stop = False

    def work(u):
        if not allowed_by_robots(u):
            info(dgreen(f"    [robots] ignoré : {u}"))
            return None
        try:
            if paste_raw(u):
                return scrape_paste(u)
            pg = scrape_page(u)
            info(green(f"[+] {u}") + dgreen(f"  ({len(pg.get('links', []))} liens, {len(pg.get('items', []))} items)"))
            return pg
        except Exception as e:
            info(f"[!] {u} : {e}")
            return None

    while level and not stop:
        batch = []
        for u in level:
            if u not in seen and len(seen) < ARGS.max_pages:
                seen.add(u)
                batch.append(u)
        if not batch:
            break
        with ThreadPoolExecutor(max_workers=ARGS.threads) as ex:
            got = [g for g in ex.map(work, batch) if g]
        pages += got
        if depth >= ARGS.depth:
            break
        nxt = []
        for pg in got:
            base = pg["url"]
            for u in pg.get("_all_links", []):
                if ARGS.any_domain or host(u) == host(base):
                    nxt.append(u.split("#")[0])
        level = uniq(nxt)
        depth += 1
    for pg in pages:
        pg.pop("_all_links", None)
    return pages


# ---------------------------------------------------------------- listes texte
_OCT = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
AS_PATTERNS = {
    "ips": re.compile(rf"\b(?:{_OCT}\.){{3}}{_OCT}\b"),
    "ipport": re.compile(rf"\b(?:{_OCT}\.){{3}}{_OCT}:\d{{2,5}}\b"),
    "domains": re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b", re.I),
    "emails": EMAIL_RE,
    "urls": URL_RE,
    "hashes": re.compile(r"\b(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32})\b"),
    "numbers": re.compile(r"\b\d+\b"),
    "words": re.compile(r"[^\W\d_]{2,}"),
}


def to_raw_url(url):
    """blob GitHub -> raw.githubusercontent ; sites de paste -> contenu brut."""
    m = re.match(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/blob/(.+)", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return paste_raw(url) or url


def looks_html(body, ctype):
    if "html" in ctype.lower():
        return True
    return body.lstrip()[:1] == "<" and bool(re.search(r"<(html|body|div|ul|ol|li|pre|table|p)\b", body[:5000], re.I))


def read_source(url):
    """-> (texte, content_type) depuis stdin (-), un fichier local ou une URL."""
    if url == "-":
        return sys.stdin.read(ARGS.max_bytes), "text/plain"
    if os.path.isfile(url):
        with open(url, encoding="utf-8", errors="replace") as f:
            return f.read(ARGS.max_bytes), "text/plain"
    body, _, ctype = fetch_c(to_raw_url(url))
    return body, ctype


def raw_text_lines(url):
    """Lignes brutes d'une source : fichier texte -> chaque ligne ; page HTML -> pre/li/tableaux/texte."""
    kind = doc_kind(url)
    if kind and url != "-" and not os.path.isfile(url):
        data, _, _ = fetch(url, binary=True, max_bytes=DOC_MAX)
        return extract_doc_text(data, kind).splitlines()
    body, ctype = read_source(url)
    kind = None if url == "-" or os.path.isfile(url) else sniff_doc_kind(body, ctype)
    if kind:
        data, _, _ = fetch(to_raw_url(url), binary=True, max_bytes=DOC_MAX)
        return extract_doc_text(data, kind).splitlines()
    root = XML_ROOT_RE.match(body[:3000])
    if root:
        if root.group(1).lower() in ("urlset", "sitemapindex"):
            return [l["url"] for l in sitemap_page(url, direct=True)["links"]]
        return [e["url"] or e["title"] for e in parse_feed(body, url)["entries"]]
    if host(url) in HTML_PASTE_SITES or looks_html(body, ctype):
        p = PageParser(url)
        p.feed(body)
        pre = [l for blk in p.pre for l in blk.splitlines()]
        col1 = best_column(p.tables, p.table_headers) or [row[0] for t, hd in zip(p.tables, p.table_headers)
                                                          for row, h in zip(t, hd) if row and not h]
        # plus grande liste hors interface (menus, sélecteurs de langue, pied de page...)
        content = [l for ui, l in p.lists if not ui]
        biggest = max(content or [l for _, l in p.lists], key=len, default=[])
        cands = {"pre": pre, "li": p.items_main if ARGS.main else p.items, "table": col1,
                 "text": p.main_pieces() if ARGS.main else p.text}
        want = [w.strip() for w in ARGS.text_from.split(",")]
        if want == ["auto"]:  # la plus riche entre bloc pre / liste principale / tableau, sinon le texte
            cands["li"] = biggest
            best = max(("pre", "li", "table"), key=lambda k: len(cands[k]))
            return cands[best] if len(cands[best]) >= 3 else cands["text"]
        return [l for w in want for l in cands.get(w, [])]
    return body.splitlines()


def clean_lines(lines):
    out = []
    for l in lines:
        l = l.strip()
        if not l or (ARGS.strip_comments and l.startswith(("#", ";", "//"))):
            continue
        out.append(l)
    if ARGS.text_as != "lines":
        rx = AS_PATTERNS[ARGS.text_as]
        out = [m if isinstance(m, str) else m[0] for l in out for m in rx.findall(l)]
        if ARGS.text_as in ("domains", "emails"):
            out = [m.lower() for m in out]
    return [l for l in out if ARGS.min_len <= len(l) <= ARGS.max_len and text_ok(l)]


def build_textlist(sources):
    sources = uniq(sources)
    agg = WordAgg()
    live = LiveView("liste en direct", agg, total=len(sources), show_top=False)

    def work(u):
        live.src(u, "run")
        try:
            lines = clean_lines(raw_text_lines(u))
            agg.add(lines, u)
            live.src(u, "ok", len(lines))
            info(green(f"[+] {u if len(u) < 90 else u[:87] + '...'}") + dgreen(f"  ({len(lines)} entrées)"))
            return u, lines, None
        except Exception as e:
            live.src(u, "err")
            info(f"[!] {u} : {e}")
            return u, [], str(e)
    live.start()
    try:
        with ThreadPoolExecutor(max_workers=ARGS.threads) as ex:
            res = list(ex.map(work, sources))
    finally:
        live.stop()
    items, seen = [], set()
    for u, lines, _ in res:
        for l in lines:
            if ARGS.no_unique or l not in seen:
                seen.add(l)
                items.append({"line": l, "source": u})
    if ARGS.sort:
        items.sort(key=lambda i: i["line"].lower())
    items = items[: ARGS.max_lines]
    info(green(f"[*] {len(items)} entrées au total ({len(res)} sources)"))
    return {"sources": [{"url": u, "count": len(l), "error": e} for u, l, e in res], "count": len(items), "items": items}


def save_textlist(path, tl):
    ext = os.path.splitext(path)[1].lower()
    lines = [i["line"] for i in tl["items"]]
    with open(path, "w", newline="", encoding="utf-8") as f:
        if ext == ".json":
            json.dump(tl, f, ensure_ascii=False, indent=2)
        elif ext == ".csv":
            w = SafeCsv(csv.writer(f))
            w.writerow(["source", "entry"])
            w.writerows([i["source"], i["line"]] for i in tl["items"])
        elif ext == ".md":
            f.write("\n".join(f"- {md_text(l)}" for l in lines) + "\n")
        elif ext in (".html", ".htm"):
            f.write("<!doctype html><meta charset=utf-8><title>scrapaud</title><ul>\n"
                    + "\n".join(f"<li>{ihtml.escape(l)}</li>" for l in lines) + "\n</ul>\n")
        else:
            f.write("\n".join(lines) + ("\n" if lines else ""))
    info(green(f"[+] sauvegardé : {path}"))


# -------------------------------------------------------------------- pastes
PASTE_DOMAINS = ["pastebin.com", "gist.github.com", "dpaste.com", "dpaste.org", "rentry.co", "paste.ee",
                 "bpa.st", "paste.debian.net", "paste.rs", "hst.sh", "pastes.dev", "pastefy.app",
                 "pastebin.pl", "ideone.com", "gitlab.com", "sprunge.us", "termbin.com",
                 "hasteb.in", "paste.helpch.at", "mclo.gs", "hackmd.io",
                 "justpaste.it", "controlc.com", "pastelink.net", "telegra.ph"]
# sites sans URL "raw" : on lit la page HTML et on en extrait le texte
HTML_PASTE_SITES = {"justpaste.it", "controlc.com", "pastelink.net", "telegra.ph"}
SYNTAXES = ["text", "python", "php", "javascript", "json", "bash", "java", "c", "cpp", "csharp", "html5",
            "sql", "xml", "yaml", "css", "lua", "perl", "ruby", "go", "powershell", "dos", "ini", "markdown", "rust"]


def paste_raw(url):
    """URL du contenu brut si `url` est un paste d'un site connu, sinon None."""
    p = urllib.parse.urlparse(url)
    h = host(url)
    parts = [x for x in p.path.split("/") if x]
    base = f"{p.scheme}://{p.netloc}"
    if not parts or p.scheme not in ("http", "https"):
        return None
    one = len(parts) == 1
    if h == "pastebin.com":
        if one and re.fullmatch(r"[A-Za-z0-9]{8}", parts[0]):
            return f"{base}/raw/{parts[0]}"
        if len(parts) == 2 and parts[0] == "raw":
            return url
    elif h == "gist.github.com":
        if len(parts) in (1, 2) and re.fullmatch(r"[0-9a-f]{20,}", parts[-1]):
            return f"{base}/{'/'.join(parts)}/raw"
    elif h == "dpaste.com" and one:
        return f"{base}/{parts[0].removesuffix('.txt')}.txt"
    elif h == "mclo.gs" and one:
        return f"https://api.mclo.gs/1/raw/{parts[0]}"
    elif h == "hackmd.io" and (one or (len(parts) == 2 and parts[0].startswith("@"))) and parts[0] != "download":
        return f"{base}/{'/'.join(parts)}/download"
    elif h in ("dpaste.org", "bpa.st", "hasteb.in", "paste.helpch.at") \
            and one and parts[0] != "raw":
        return f"{base}/raw/{parts[0]}" if h != "dpaste.org" else f"{base}/{parts[0]}/raw"
    elif h in ("rentry.co", "rentry.org") and one and parts[0] != "raw":
        return f"{base}/{parts[0]}/raw"
    elif h == "paste.ee" and len(parts) == 2 and parts[0] in ("p", "r"):
        return f"{base}/r/{parts[1]}"
    elif h == "paste.debian.net" and parts[-1].isdigit():
        return f"{base}/plain/{parts[-1]}"
    elif h in ("paste.rs", "sprunge.us", "termbin.com", "gist.githubusercontent.com") and parts:
        return url
    elif h == "hst.sh" and one and parts[0] != "raw":
        return f"{base}/raw/{parts[0]}"
    elif h == "pastes.dev" and one:
        return f"https://api.pastes.dev/{parts[0]}"
    elif h == "pastefy.app" and one and parts[0] != "raw":
        return f"{base}/{parts[0]}/raw"
    elif h == "pastebin.pl" and len(parts) == 2 and parts[0] == "view":
        return f"{base}/view/raw/{parts[1]}"
    elif h == "ideone.com" and one and parts[0] != "plain":
        return f"{base}/plain/{parts[0]}"
    elif h == "gitlab.com" and "snippets" in parts and parts[-1].isdigit():
        return f"{base}/{'/'.join(parts)}/raw"
    elif h in HTML_PASTE_SITES and one:
        return url
    return None



def paste_slug(text, n=40):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:n]


def _mkdir_private(path):
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o700)


def save_paste_file(rec, body):
    """Écrit le paste COMPLET dans <dir>/<site>/<AAAAMMJJ>/<id>_<titre>.txt et l'ajoute à <dir>/index.md.
    Droits 700/600 (un paste peut contenir des données sensibles). Ne réécrit jamais un fichier existant.
    -> chemin du fichier, ou None (disque trop plein / erreur)."""
    root = os.path.abspath(os.path.expanduser(ARGS.paste_dir))
    now = datetime.datetime.now()
    site = paste_slug(rec["site"], 40) or "site"
    pid = re.sub(r"[^A-Za-z0-9._-]+", "_", urllib.parse.urlparse(rec["url"]).path.rstrip("/").rsplit("/", 1)[-1]).strip("._")[:40] or "paste"
    title = paste_slug(rec.get("title") or "", 40)
    base = f"{pid}_{title}" if title and title != paste_slug(pid) else pid
    folder = os.path.join(root, site, now.strftime("%Y%m%d"))
    header = "".join(f"{k:<9}: {v}\n" for k, v in (
        ("source", rec["url"]), ("brut", rec["raw_url"]), ("site", rec["site"]), ("titre", rec.get("title") or ""),
        ("syntaxe", rec.get("syntax") or ""), ("publié", rec.get("posted") or ""),
        ("récupéré", now.strftime("%Y-%m-%d %H:%M")), ("taille", f"{len(body.encode('utf-8', 'replace'))} o")) if v)
    text = header + "-" * 64 + "\n" + body + ("" if body.endswith("\n") else "\n")
    with _paste_lock:
        if free_space(root if os.path.exists(root) else os.path.dirname(root)) < len(text.encode("utf-8", "replace")) + 100 * 2**20:
            info("[!] --paste-dir : espace disque insuffisant (marge de 100 Mo), paste non enregistré")
            return None
        for d in (root, os.path.join(root, site), folder):
            _mkdir_private(d)
        n, path = 1, None
        while True:
            path = os.path.join(folder, base + ("" if n == 1 else f"-{n}") + ".txt")
            assert os.path.realpath(path).startswith(os.path.realpath(root) + os.sep)      # jamais hors du dossier choisi
            if not os.path.exists(path):
                break
            with open(path, encoding="utf-8", errors="replace") as f:
                if f.readline().strip() == f"{'source':<9}: {rec['url']}":                  # déjà enregistré : on ne recopie pas
                    return path
            n += 1
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as f:
            f.write(text)
        index = os.path.join(root, "index.md")
        new = not os.path.exists(index)
        with open(index, "a", encoding="utf-8") as f:
            if new:
                f.write("# Pastes récupérés par scrapaud\n\n")
                os.chmod(index, 0o600)
            rel = urllib.parse.quote(os.path.relpath(path, root))
            f.write(f"- {now:%Y-%m-%d %H:%M} · {md_text(rec['site'])} · [{md_text(rec.get('title') or pid)}]({rel})"
                    f" — {md_text(rec['url'])} · {len(body)} o" + (f" · {len(rec['matches'])} correspondance(s)" if rec.get("matches") else "") + "\n")
    return path


_paste_lock = threading.Lock()


def scrape_paste(url, title="", extra=None):
    """Télécharge un paste en brut -> dict, ou None s'il est écarté par --grep/--exclude."""
    raw = paste_raw(url) or url
    body, _, ctype = fetch_c(raw, retries=1)
    if host(url) in HTML_PASTE_SITES:
        pp = PageParser(raw)
        pp.feed(body)
        body = "\n".join(pp.text)
        title = title or " ".join(pp.title.split())
    elif "html" in ctype.lower() and re.match(r"\s*<(!doctype|html)", body, re.I):
        raise ValueError("réponse HTML au lieu du texte brut (paste supprimé ou accès bloqué)")
    if not text_ok(title, body) or (ARGS._paste_q and not ARGS._paste_q.search(title + "\n" + body)):
        return None
    rec = {"type": "paste", "url": url, "raw_url": raw, "site": host(url), "title": title, "size": len(body)}
    rec.update(extra or {})
    rx = ARGS._grep or ARGS._paste_q
    rec["matches"] = [l.strip()[:300] for l in body.splitlines() if rx and rx.search(l)][:50]
    if "emails" in ARGS._extract:
        rec["emails"] = sorted(set(EMAIL_RE.findall(body)))
    if "links" in ARGS._extract:
        rec["links"] = [{"url": u.rstrip(".,;"), "text": ""} for u in uniq(URL_RE.findall(body))
                        if link_ok({"url": u}, url)][:200]
    if ARGS.paste_content > 0:
        rec["content"] = body[: ARGS.paste_content]
    if ARGS.paste_dir:
        rec["file"] = save_paste_file(rec, body)          # contenu COMPLET, pas la version tronquée de --paste-content
    return rec


PASTE_MAX_FAILS = 3


def fetch_pastes(cands):
    """cands : liste de (url, titre, extra). Téléchargement en parallèle limité (pastebin bannit vite)."""
    fails, lock = {}, threading.Lock()      # échecs CONSÉCUTIFS par site : on n'insiste pas sur un site qui refuse

    def work(c):
        url, title, extra = c
        h = host(url)
        with lock:
            if fails.get(h, 0) >= PASTE_MAX_FAILS:
                if fails[h] == PASTE_MAX_FAILS:
                    fails[h] += 1
                    info(f"[!] {h} : {PASTE_MAX_FAILS} échecs consécutifs (bloqué ?) : site ignoré pour cette passe")
                return None
        try:
            rec = scrape_paste(url, title, extra)
            time.sleep(max(ARGS.delay, 0.8))
            with lock:
                fails[h] = 0
            if rec:
                info(green(f"[+] paste {url}") + dgreen(f"  ({rec['size']} o) {title[:50]}"))
            return rec
        except Exception as e:
            gone = isinstance(e, urllib.error.HTTPError) and e.code in (404, 410)     # paste expiré : normal, pas un blocage
            if not gone:
                with lock:
                    fails[h] = fails.get(h, 0) + 1
            info(f"[!] paste {url} : {e}")
            return None
    with ThreadPoolExecutor(max_workers=min(ARGS.threads, 3)) as ex:
        return [r for r in ex.map(work, cands) if r]


def pastebin_archive(syntaxes):
    """Liste des pastes publics récents de pastebin.com (/archive, /archive/<syntaxe>)."""
    out = []
    for syn in syntaxes:
        u = "https://pastebin.com/archive" + (f"/{syn}" if syn else "")
        try:
            h, _, _ = fetch(u)
        except Exception as e:
            info(f"[!] {u} : {e}")
            continue
        n = 0
        for blk in h.split("<div data-key=")[1:]:
            m = re.search(r'href="/([A-Za-z0-9]{8})(?:\?[^"]*)?">(.*?)</a>', blk, re.S)
            if not m:
                continue
            when = re.search(r'td_right">\s*(.*?)\s*</td>', blk, re.S)
            sy = re.search(r'/archive/([^"/]+)"', blk)
            out.append({"id": m.group(1), "title": clean(m.group(2)), "posted": clean(when.group(1)) if when else "",
                        "syntax": sy.group(1) if sy else (syn or "")})
            n += 1
        info(dgreen(f"    archive {syn or 'principale'} : {n} pastes listés"))
    return uniq(out, key=lambda r: r["id"])


def gists_public(pages):
    """Derniers gists publics via l'API GitHub (60 req/h sans jeton ; GITHUB_TOKEN pour plus)."""
    out = []
    hdr = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        hdr["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    for page in range(1, pages + 1):
        try:
            txt, _, _ = fetch(f"https://api.github.com/gists/public?per_page=100&page={page}", want_json=True, headers=hdr)
        except Exception as e:
            info(f"[!] gists p{page} : {e}")
            break
        for g in json.loads(txt):
            for name, f in (g.get("files") or {}).items():
                if f.get("raw_url") and (f.get("size") or 0) <= ARGS.max_bytes:
                    out.append((f["raw_url"], f"{name} - {g.get('description') or ''}".strip(" -"),
                                {"gist": g.get("html_url"), "posted": g.get("created_at", ""), "syntax": f.get("language") or ""}))
    info(dgreen(f"    gists publics : {len(out)} fichiers listés"))
    return out


def collect_pastes(queries, seen):
    """Une passe complète : recherche sur les sites de paste + archive pastebin. -> nouveaux pastes."""
    cands = []
    if ARGS.pastes:
        sites = ARGS._paste_sites
        old_site = ARGS.site
        try:
            for q in queries:
                for dom in sites:
                    ARGS.site = dom
                    info(green(f"[*] paste : « {q} » sur {dom}"))
                    for r in search(q):
                        if paste_raw(r["url"]):
                            cands.append((r["url"], r["title"], {"query": q, "engine": r["engine"]}))
        finally:
            ARGS.site = old_site
        if not cands:
            info("[!] aucun paste trouvé via les moteurs (DuckDuckGo/Bing bloqués ou sans résultat) : "
                 "réessaie plus tard, utilise --proxy, ou --pastebin pour scanner l'archive directement")
    if ARGS.pastebin:
        syn = SYNTAXES if ARGS.archive_syntax == "all" else [s.strip() for s in ARGS.archive_syntax.split(",")]
        for a in pastebin_archive([""] if not ARGS.archive_syntax else syn):
            cands.append((f"https://pastebin.com/{a['id']}", a["title"],
                          {"posted": a["posted"], "syntax": a["syntax"]}))
    if ARGS.gists:
        cands += gists_public(ARGS.gist_pages)
    cands = [c for c in uniq(cands, key=lambda c: c[0]) if c[0] not in seen][: ARGS.paste_max]
    seen.update(c[0] for c in cands)
    info(green(f"[*] {len(cands)} pastes à lire"))
    if ARGS.titles_only:
        return [{"type": "paste", "url": u, "raw_url": paste_raw(u) or u, "site": host(u), "title": t, "size": 0,
                 "matches": [], **e} for u, t, e in cands if text_ok(t)]
    return fetch_pastes(cands)


# ------------------------------------------------------------------- moteurs
class DDGParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results, self._cur, self._snip = [], None, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "a" and "result__a" in cls:
            href = a.get("href", "")
            if href.startswith("//"):
                href = "https:" + href
            q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            if "uddg" in q:
                href = q["uddg"][0]
            self._cur = {"title": "", "url": href, "snippet": ""}
        elif tag == "a" and "result__snippet" in cls and self.results:
            self._snip = True

    def handle_endtag(self, tag):
        if tag == "a":
            if self._cur:
                self._cur["title"] = " ".join(self._cur["title"].split())
                self.results.append(self._cur)
                self._cur = None
            self._snip = False

    def handle_data(self, data):
        if self._cur is not None:
            self._cur["title"] += data
        elif self._snip and self.results:
            self.results[-1]["snippet"] += data


def clean(s):
    return " ".join(ihtml.unescape(re.sub(r"<[^>]+>", "", s or "")).split())


def build_query(q):
    parts = [q]
    if ARGS.site:
        parts.append(f"site:{ARGS.site}")
    if ARGS.filetype:
        parts.append(f"filetype:{ARGS.filetype}")
    return " ".join(parts)


def eng_ddg(q, page):
    if page > 1:
        return []
    body = urllib.parse.urlencode({"q": build_query(q), "kl": "fr-fr" if ARGS.lang == "fr" else "wt-wt"}).encode()
    html, _, _ = fetch("https://html.duckduckgo.com/html/", data=body, retries=1)
    p = DDGParser()
    p.feed(html)
    for r in p.results:
        r["snippet"] = clean(r["snippet"])
    return [r for r in p.results if r["url"].startswith("http") and "duckduckgo.com/y.js" not in r["url"]]


def _bing_real_url(href):
    u = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u", [""])[0]
    if u.startswith("a1"):
        try:
            b = u[2:]
            return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode()
        except Exception:
            pass
    return href


def eng_bing(q, page):
    qs = urllib.parse.urlencode({"q": build_query(q), "setlang": ARGS.lang, "first": (page - 1) * 10 + 1})
    html, _, _ = fetch(f"https://www.bing.com/search?{qs}")
    out = []
    for blk in html.split('<li class="b_algo')[1:]:
        m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not m:
            continue
        url = _bing_real_url(ihtml.unescape(m.group(1)))
        sn = re.search(r"<p[^>]*>(.*?)</p>", blk, re.S)
        if url.startswith("http"):
            out.append({"title": clean(m.group(2)), "url": url, "snippet": clean(sn.group(1)) if sn else ""})
    return [r for r in out if operators_ok(r["url"])]


def operators_ok(url):
    """Applique site:/filetype: côté client pour les moteurs qui les ignorent."""
    if ARGS.site and ARGS.site.lower() not in host(url):
        return False
    if ARGS.filetype and "." + ARGS.filetype.lower().lstrip(".") not in url.lower():
        return False
    return True


def eng_wikipedia(q, page):
    qs = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": q, "format": "json",
                                 "srlimit": 20, "sroffset": (page - 1) * 20})
    txt, _, _ = fetch(f"https://{ARGS.lang}.wikipedia.org/w/api.php?{qs}", want_json=True)
    return [{"title": r["title"],
             "url": f"https://{ARGS.lang}.wikipedia.org/wiki/{urllib.parse.quote(r['title'].replace(' ', '_'))}",
             "snippet": clean(r.get("snippet"))} for r in json.loads(txt)["query"]["search"]]


def eng_github(q, page):
    qs = urllib.parse.urlencode({"q": q, "per_page": 20, "page": page})
    txt, _, _ = fetch(f"https://api.github.com/search/repositories?{qs}", want_json=True, headers={"Accept": "application/vnd.github+json"})
    return [{"title": r["full_name"], "url": r["html_url"],
             "snippet": f"★{r['stargazers_count']} {r.get('description') or ''}".strip()} for r in json.loads(txt)["items"]]


def eng_hn(q, page):
    qs = urllib.parse.urlencode({"query": q, "page": page - 1, "hitsPerPage": 20})
    txt, _, _ = fetch(f"https://hn.algolia.com/api/v1/search?{qs}", want_json=True)
    out = []
    for r in json.loads(txt)["hits"]:
        url = r.get("url") or f"https://news.ycombinator.com/item?id={r['objectID']}"
        out.append({"title": r.get("title") or r.get("story_title") or "", "url": url,
                    "snippet": f"{r.get('points', 0)} pts, {r.get('num_comments', 0)} comm."})
    return out


def eng_archive(q, page):
    qs = urllib.parse.urlencode({"q": q, "fl[]": "identifier,title,description", "rows": 20, "page": page, "output": "json"})
    txt, _, _ = fetch(f"https://archive.org/advancedsearch.php?{qs}", want_json=True)
    out = []
    for r in json.loads(txt)["response"]["docs"]:
        d = r.get("description", "")
        d = d[0] if isinstance(d, list) and d else d
        out.append({"title": str(r.get("title", r["identifier"])), "url": f"https://archive.org/details/{r['identifier']}",
                    "snippet": clean(d if isinstance(d, str) else "")[:200]})
    return out


def eng_searxng(q, page):
    """Instance SearXNG (auto-hébergée) : agrège plusieurs moteurs. Nécessite `formats: [html, json]` dans settings.yml."""
    base = (ARGS.searx or "").rstrip("/")
    if not base:
        raise ValueError("aucune instance SearXNG : utilise --searx URL ou la variable SCRAPAUD_SEARX")
    params = {"q": build_query(q), "format": "json", "pageno": page, "language": ARGS.lang}
    if ARGS.category:
        params["categories"] = ",".join(CATEGORY_ALIASES.get(c, c) for c in ARGS._categories)
    if ARGS.since:
        params["time_range"] = ARGS.since
    if ARGS.searx_engines:
        params["engines"] = ARGS.searx_engines
    try:
        txt, _, _ = fetch(f"{base}/search?{urllib.parse.urlencode(params)}", want_json=True, retries=1)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise ValueError("SearXNG refuse le format json : ajoute `json` à search.formats dans settings.yml") from e
        raise
    out = []
    for r in json.loads(txt).get("results", []):
        eng = ",".join(r.get("engines") or [])
        extra = " ".join(x for x in ((r.get("publishedDate") or "")[:10], r.get("resolution") or "") if x)
        res = {"title": clean(r.get("title")), "url": r.get("url", ""),
               "snippet": (extra + " " if extra else "") + clean(r.get("content")) + (f" [{eng}]" if eng else "")}
        if r.get("img_src"):
            res["image"] = r["img_src"]
            res["snippet"] = f"{res['snippet']} img: {r['img_src']}".strip()
        out.append(res)
    return [r for r in out if r["url"].startswith("http") and operators_ok(r["url"])]



AHMIA_BASES = ["https://ahmia.fi/search/?",
               "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?"]


def eng_ahmia(q, page):
    """Ahmia : moteur d'indexation de services .onion (filtre les contenus d'abus). Repli sur son miroir onion via Tor."""
    if page > 1:
        return []
    last = None
    for base in AHMIA_BASES:
        try:
            html, _, _ = fetch(base + urllib.parse.urlencode({"q": q}), retries=1)
            tok = re.search(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html)
            if tok:  # Ahmia exige le jeton caché du formulaire
                html, _, _ = fetch(base + urllib.parse.urlencode({"q": q, tok.group(1): tok.group(2)}), retries=1)
            break
        except Exception as e:
            last = e
            info(dgreen(f"    ahmia ({'onion' if '.onion' in base else 'clearnet'}) : {e}"))
    else:
        raise last
    out = []
    for blk in html.split('<li class="result')[1:]:
        a = re.search(r'<h4>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not a:
            continue
        href = ihtml.unescape(a.group(1))
        url = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("redirect_url", [href])[0]
        sn = re.search(r"<p>(.*?)</p>", blk, re.S)
        if ".onion" in url:
            out.append({"title": clean(a.group(2)), "url": url, "snippet": clean(sn.group(1)) if sn else ""})
    return out


def eng_gitlab(q, page):
    qs = urllib.parse.urlencode({"search": q, "per_page": 20, "page": page, "order_by": "last_activity_at"})
    txt, _, _ = fetch(f"https://gitlab.com/api/v4/projects?{qs}", want_json=True)
    return [{"title": r["path_with_namespace"], "url": r["web_url"],
             "snippet": f"★{r.get('star_count', 0)} {r.get('description') or ''}".strip()} for r in json.loads(txt)]


def eng_stackexchange(q, page):
    qs = urllib.parse.urlencode({"q": q, "site": ARGS.se_site, "pagesize": 20, "page": page,
                                 "order": "desc", "sort": "relevance"})
    txt, _, _ = fetch(f"https://api.stackexchange.com/2.3/search/advanced?{qs}", want_json=True)
    return [{"title": clean(r["title"]), "url": r["link"],
             "snippet": f"{r.get('score', 0)} votes, {r.get('answer_count', 0)} réponses"
                        + (" ✔" if r.get("is_answered") else "")} for r in json.loads(txt).get("items", [])]


def _domain_of(q):
    q = q.strip().lower()
    q = re.sub(r"^https?://", "", q).split("/")[0]
    return q if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", q) else None


def eng_wayback(q, page):
    """Pages archivées (Wayback Machine, CDX). `q` = domaine ou préfixe d'URL."""
    if page > 1:
        return []
    dom = _domain_of(q)
    params = {"url": dom if dom else q, "output": "json", "fl": "timestamp,original,mimetype",
              "collapse": "urlkey", "filter": "statuscode:200", "limit": 300}
    if dom and "/" not in q.strip().replace("https://", "").replace("http://", "").rstrip("/"):
        params["matchType"] = "domain"
    txt, _, _ = fetch("https://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(params), want_json=True)
    rows = json.loads(txt or "[]")[1:]
    return [{"title": r[1], "url": f"https://web.archive.org/web/{r[0]}/{r[1]}", "snippet": f"{r[0][:8]} {r[2]}"} for r in rows]


def eng_crtsh(q, page):
    """Sous-domaines connus via la transparence des certificats (crt.sh). `q` = domaine."""
    if page > 1:
        return []
    dom = _domain_of(q)
    if not dom:
        raise ValueError("crtsh attend un nom de domaine (ex. exemple.com)")
    txt, _, _ = fetch("https://crt.sh/?" + urllib.parse.urlencode({"q": f"%.{dom}", "output": "json"}), want_json=True)
    names = set()
    for r in json.loads(txt or "[]"):
        for n in r.get("name_value", "").splitlines():
            n = n.strip().lower().lstrip("*.")
            if n.endswith(dom) and re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", n):
                names.add(n)
    return [{"title": n, "url": f"https://{n}", "snippet": "certificat public (CT log)"} for n in sorted(names)]



_arxiv_last = [0.0]


def eng_arxiv(q, page):
    """Articles arXiv (API Atom officielle ; elle exige ≥3 s entre deux appels, sinon 406/429)."""
    wait = 3.2 - (time.time() - _arxiv_last[0])
    if wait > 0:
        time.sleep(wait)
    _arxiv_last[0] = time.time()
    # arXiv refuse ":" encodé (%3A) : la requête est assemblée à la main (all:mot+AND+all:mot)
    sq = "+AND+".join("all:" + urllib.parse.quote_plus(w) for w in q.split()) or "all:*"
    xml, _, _ = fetch(f"https://export.arxiv.org/api/query?search_query={sq}&start={(page - 1) * 20}&max_results=20",
                      headers={"Accept": "application/atom+xml, */*"})
    if "<!ENTITY" in xml:
        raise ValueError("réponse refusée (entités XML)")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(xml.encode("utf-8")).findall("a:entry", ns):
        out.append({"title": clean(e.findtext("a:title", "", ns)), "url": (e.findtext("a:id", "", ns) or "").strip(),
                    "snippet": (e.findtext("a:published", "", ns) or "")[:10] + " " + clean(e.findtext("a:summary", "", ns))[:240]})
    return out


def eng_openalex(q, page):
    """Publications scientifiques (OpenAlex, API ouverte)."""
    qs = urllib.parse.urlencode({"search": q, "per-page": 20, "page": page})
    txt, _, _ = fetch(f"https://api.openalex.org/works?{qs}", want_json=True)
    out = []
    for r in json.loads(txt).get("results", []):
        venue = ((r.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        url = r.get("doi") or r.get("id") or ""
        out.append({"title": clean(r.get("display_name")), "url": url,
                    "snippet": f"{r.get('publication_year', '')} · {r.get('cited_by_count', 0)} citations · {venue}".strip(" ·")})
    return out


CATEGORY_ALIASES = {"social": "social media", "video": "videos", "image": "images", "actu": "news", "sciences": "science"}
ENGINES = {"searxng": eng_searxng, "bing": eng_bing, "ddg": eng_ddg, "wikipedia": eng_wikipedia,
           "github": eng_github, "hn": eng_hn, "archive": eng_archive, "gitlab": eng_gitlab,
           "stackexchange": eng_stackexchange, "ahmia": eng_ahmia, "wayback": eng_wayback, "crtsh": eng_crtsh,
           "arxiv": eng_arxiv, "openalex": eng_openalex}
SPECIAL_ENGINES = {"ahmia", "wayback", "crtsh", "arxiv", "openalex"}   # spécialisés : jamais inclus dans -e all, à nommer explicitement
AUTO_ORDER = ["bing", "ddg", "wikipedia"]


TRACK_RE = re.compile(r"^(utm_.*|fbclid|gclid|dclid|msclkid|yclid|igshid|mc_cid|mc_eid|_ga|ref|ref_src|spm)$", re.I)


def norm_url(u):
    """Clé de dédoublonnage : sans schéma, sans www, sans fragment ni paramètres de suivi, sans / final."""
    p = urllib.parse.urlparse(u)
    q = sorted((k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not TRACK_RE.match(k))
    path = re.sub(r"/index\.(?:html?|php)$", "/", p.path).rstrip("/") or "/"
    return p.netloc.lower().removeprefix("www.") + path + ("?" + urllib.parse.urlencode(q) if q else "")


def rrf_merge(ranked, k=60):
    """Fusion « Reciprocal Rank Fusion » : un résultat trouvé par plusieurs moteurs, et bien classé, remonte.
    ranked = [(moteur, [résultats dans l'ordre])] -> liste triée par score décroissant."""
    merged = {}
    for name, res in ranked:
        for rank, r in enumerate(res):
            key = norm_url(r["url"])
            m = merged.get(key)
            if m is None:
                m = merged[key] = dict(r, engines=[], score=0.0)
            if name not in m["engines"]:
                m["engines"].append(name)
            m["score"] += 1.0 / (k + rank + 1)
            if len(r.get("snippet") or "") > len(m.get("snippet") or ""):
                m["snippet"] = r["snippet"]
            if not m.get("title") and r.get("title"):
                m["title"] = r["title"]
    out = sorted(merged.values(), key=lambda m: (-m["score"], m["url"]))
    for m in out:
        m["engine"] = ",".join(m["engines"])
        m["score"] = round(m["score"], 5)
    return out


_dead = {}          # moteur -> instant jusqu'auquel on l'ignore (anti-bot détecté)
DEAD_FOR = 600


def engine_is_dead(name):
    return _dead.get(name, 0) > time.time()


def run_engine(name, query):
    """Toutes les pages d'un moteur (avec cache). Lève l'exception du moteur si la 1re page échoue."""
    got = []
    for page in range(1, ARGS.pages + 1):
        key = cache_key("eng", name, query, page, ARGS.site, ARGS.filetype, ARGS.lang, ARGS.category, ARGS.since,
                        ARGS.se_site, ARGS.searx_engines, ARGS.searx if name == "searxng" else "")
        r = cache_get(key)
        if r is None:
            try:
                r = ENGINES[name](query, page)
            except Exception as e:
                if page > 1:
                    info(f"[!] {name} p{page} : {e}")
                    break
                if isinstance(e, urllib.error.HTTPError) and e.code in (403, 406, 429, 503):
                    _dead[name] = time.time() + DEAD_FOR   # moteur bloqué : inutile de réessayer tout de suite
                raise
            if r:
                cache_put(key, r)
        if not r:
            break
        got += r
    return got


def search(query):
    names = ARGS._engines
    if ARGS.onion and names == ["auto"]:
        names = ["ahmia"]
    if ARGS.category and names == ["auto"]:
        if ARGS.searx:
            names = ["searxng"]
        elif set(ARGS._categories) == {"science"}:
            names = ["arxiv", "openalex"]
        else:
            info("[!] --category demande SearXNG (--searx URL) ; sans lui seul « science » est géré (arXiv + OpenAlex)")
            return []
    ranked = []
    if names == ["auto"]:
        # repli séquentiel : le 1er moteur qui répond gagne. Bing ignore site:/filetype: -> DDG d'abord dans ce cas
        order = ["ddg", "bing"] if (ARGS.site or ARGS.filetype) else list(AUTO_ORDER)
        if ARGS.searx:  # instance perso configurée -> prioritaire, pas de blocage anti-bot
            order.insert(0, "searxng")
        for name in order:
            if engine_is_dead(name):
                info(dgreen(f"    {name} : ignoré (bloqué récemment)"))
                continue
            try:
                got = run_engine(name, query)
            except Exception as e:
                info(f"[!] {name} : {e}")
                continue
            if got:
                info(green(f"[*] {name} : {len(got)} résultats"))
                ranked.append((name, got))
                break
            info(dgreen(f"    {name} : aucun résultat, moteur suivant..."))
    else:
        order = ([e for e in ENGINES if e not in SPECIAL_ENGINES and (e != "searxng" or ARGS.searx)]
                 if names == ["all"] else names)
        order = [e for e in order if not engine_is_dead(e)] or order

        def work(name):
            try:
                return name, run_engine(name, query)
            except Exception as e:
                info(f"[!] {name} : {e}")
                return name, []
        with ThreadPoolExecutor(max_workers=min(len(order), 6)) as ex:   # moteurs interrogés en parallèle
            for name, got in ex.map(work, order):
                if got:
                    info(green(f"[*] {name} : {len(got)} résultats"))
                    ranked.append((name, got))
    for name, got in ranked:
        for r in got:
            r["query"] = query
    results = rrf_merge(ranked)
    results = [r for r in results if text_ok(r["url"], r["title"], r["snippet"])
               and not (ARGS.not_domain and any(d in host(r["url"]) for d in ARGS.not_domain))]
    return results[: ARGS.limit]


# ------------------------------------- vue en temps réel + wordlists automatiques
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class WordAgg:
    """Agrégat thread-safe : compte chaque entrée, garde les nouveautés récentes (pour la vue live)."""

    def __init__(self, keep_sources=False):
        self.lock = threading.Lock()
        self.counter = collections.Counter()     # ordre d'insertion = ordre de première apparition
        self.total = 0
        self.recent = collections.deque(maxlen=80)
        self.per_source = {} if keep_sources else None

    @property
    def unique(self):
        return len(self.counter)

    def add(self, entries, source=None):
        with self.lock:
            if self.per_source is not None and source is not None:
                ps = self.per_source.setdefault(source, collections.Counter())
                ps.update(entries)
            for e in entries:
                self.total += 1
                if e not in self.counter:
                    self.recent.append(e)
                self.counter[e] += 1

    def top(self, n=8):
        with self.lock:
            return self.counter.most_common(n)


class LiveView:
    """Tableau de bord en direct sur stderr (sources, uniques, débit, derniers mots, top).
    Inactif hors terminal / avec --quiet / --no-live : les méthodes restent alors sans effet."""

    def __init__(self, title, agg, total=0, show_top=True):
        self.title, self.agg, self.total, self.show_top = title, agg, total, show_top
        self.t0 = time.time()
        self.lock = threading.RLock()
        self.sources = collections.OrderedDict()
        self.logs = collections.deque(maxlen=3)
        self.active = False
        self._n = 0
        self._stop = threading.Event()
        self._thread = None
        self.enabled = (sys.stderr.isatty() and not ARGS.quiet and not ARGS.no_live
                        and os.environ.get("TERM", "dumb") != "dumb")

    # -- alimentation
    def src(self, url, state, count=None):
        with self.lock:
            d = self.sources.setdefault(url, {"state": state, "count": 0, "t0": time.time(), "dt": 0.0})
            d["state"] = state
            if count is not None:
                d["count"] = count
            if state != "run":
                d["dt"] = time.time() - d["t0"]

    def log(self, msg):
        with self.lock:
            self.logs.append(re.sub(r"\x1b\[[0-9;]*m", "", str(msg)))

    # -- rendu
    def frame(self, width=100, height=30):
        """Lignes (texte, style) du tableau de bord ; style : h = titre, d = discret, None = normal."""
        rows = min(max(height - 2, 8), 26)
        now = time.time()
        el = int(now - self.t0)
        fmt = lambda n: f"{n:,}".replace(",", " ")
        with self.lock:
            srcs = list(self.sources.items())
            logs = list(self.logs)
        a = self.agg
        done = sum(1 for _, d in srcs if d["state"] != "run")
        rate = a.total / max(now - self.t0, 0.5)
        L = [(f" SCRAPAUD ▸ {self.title}   {el // 60:02d}:{el % 60:02d}", "h"),
             (f" sources {done}/{max(self.total, len(srcs))} · uniques {fmt(a.unique)} · vus {fmt(a.total)} · {fmt(int(rate))}/s", None),
             (" ─ sources", "d")]
        spin = SPIN[int(now * 10) % len(SPIN)]
        room = max(2, min(6, rows - 10))
        running = [x for x in srcs if x[1]["state"] == "run"]
        finished = [x for x in srcs if x[1]["state"] != "run"][::-1]
        shown = (running + finished)[:room]

        def short(u):
            u = re.sub(r"^https?://(www\.)?", "", u)
            return u if len(u) <= width - 34 else u[: max(10, width - 37)] + "…"
        for u, d in shown:
            if d["state"] == "run":
                L.append((f" {spin} {short(u)}   lecture…", None))
            elif d["state"] == "ok":
                L.append((f" ✔ {short(u)}   {fmt(d['count'])} · {d['dt']:.1f}s", None))
            elif d["state"] == "skip":
                L.append((f" ↷ {short(u)}   ignoré", "d"))
            else:
                L.append((f" ✘ {short(u)}   erreur", "d"))
        if len(srcs) > len(shown):
            L.append((f"   … {len(srcs) - len(shown)} autres", "d"))
        recent = list(a.recent)[::-1]
        if recent and rows >= 12:
            L.append((" ─ derniers", "d"))
            line, lines = "", []
            for w in recent:
                if len(line) + len(w) + 2 > width - 4:
                    lines.append(line)
                    line = ""
                    if len(lines) == 2:
                        break
                line += ("  " if line else "") + w
            if line and len(lines) < 2:
                lines.append(line)
            L += [("  " + x, None) for x in lines]
        if self.show_top and rows >= 15:
            top = a.top(8)
            if top:
                L.append((" ─ top", "d"))
                L.append(("  " + " · ".join(f"{w} ×{c}" for w, c in top), None))
        for m in logs[-2:]:
            L.append((" ▸ " + m, "d"))
        return L[:rows]

    def draw(self):
        try:
            cols, rows = os.get_terminal_size(sys.stderr.fileno())
        except OSError:
            cols, rows = 100, 30
        out = [f"\033[{self._n}A"] if self._n else []
        frame = self.frame(cols, rows)
        for text, style in frame:
            text = text[: cols - 1]
            sgr = "\033[1;92m" if style == "h" else ("\033[32m" if style == "d" else "")
            out.append("\r\033[2K" + (sgr + text + "\033[0m" if sgr else text) + "\n")
        out.append("\033[J")
        self._n = len(frame)
        sys.stderr.write("".join(out))
        sys.stderr.flush()

    def _loop(self):
        while not self._stop.wait(0.15):
            try:
                self.draw()
            except Exception:
                pass

    def start(self):
        if not self.enabled:
            return
        LIVE[0] = self
        self.active = True
        atexit.register(lambda: sys.stderr.write("\033[?25h"))
        sys.stderr.write("\033[?25l")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        if not self.active:
            return
        self._stop.set()
        if self._thread:
            self._thread.join(1)
        try:
            self.draw()
        finally:
            sys.stderr.write("\033[?25h")
            sys.stderr.flush()
            self.active = False
            LIVE[0] = None


STOPWORDS = {
    "fr": set("""a à â abord afin ah ai aie ainsi ait allaient allons alors anterieur anterieure apres après as assez attendu au aucun
        aucune aujourd auquel aura auront aussi autre autres aux auxquelles auxquels avaient avais avait avant avec avoir avons ayant
        bah bas beaucoup bien bon c ça car ce ceci cela celle celles celui cependant certain certaine certaines certains ces cet cette
        ceux chacun chacune chaque chez ci comme comment compris concernant contre d dans de debout dedans dehors delà depuis des dès
        desormais désormais desquelles desquels dessous dessus devant devrait doit donc dont du duquel durant elle elles en encore
        enfin entre envers es est et étaient étais était étant etc été être eu eux fait faire fais faisaient fais font hormis hors
        ici il ils j je jusqu jusque l la là laquelle le lequel les lesquelles lesquels leur leurs lors lorsque lui m ma mais malgré
        me même mêmes mes moi moins mon n ne ni non nos notre nôtres nous nul on ont ou où par parce parmi pas pendant peu peut peuvent
        plus plusieurs pour pourquoi pourtant pu puis puisque qu quand quant que quel quelle quelles quelque quelques quels qui quoi
        quoique s sa sans se selon ses seront ses si sien sienne soi soit sommes son sont sous soyez sur t ta tandis te tel telle
        telles tels tes toi ton tous tout toute toutes tres très tu un une unes uns vers via voici voilà vos votre vous y""".split()),
    "en": set("""a about above after again against all am an and any are as at be because been before being below between both but by can
        cannot could did do does doing down during each few for from further had has have having he her here hers herself him himself
        his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other our ours ourselves
        out over own same she should so some such than that the their theirs them themselves then there these they this those through
        to too under until up very was we were what when where which while who whom why will with would you your yours yourself
        yourselves also however may might much must shall via yet""".split()),
    "de": set("""aber alle allem allen aller alles als also am an ander andere anderen anderer anderes auch auf aus bei bin bis bist da damit
        dann das dass daß dein deine dem den der des dessen dich die dies diese diesem diesen dieser dieses dir doch dort du durch ein
        eine einem einen einer eines einig er es etwas euch euer eure für gegen habe haben hat hatte hier hin hinter ich ihm ihn ihnen
        ihr ihre im in ist ja jede jedem jeden jeder jedes jener kann kein keine mich mir mit muss nach nicht noch nun nur ob oder ohne
        sehr sein seine sich sie sind so solche soll über um und uns unser unter vom von vor war waren warst was weil wenn werde werden
        wie wieder will wir wird wo wollen würde zu zum zur zwischen""".split()),
    "es": set("""a al algo algunas algunos ante antes como con contra cual cuando de del desde donde durante e el ella ellas ellos en entre era
        eran es esa esas ese eso esos esta estaba estado estan estar este esto estos fue fueron ha había han hasta hay la las le les lo
        los mas más me mi mis mucho muy nada ni no nos nosotros nuestra nuestro o os otra otros para pero poco por porque que quien
        quienes se sea sin sobre sois solo son soy su sus también tanto te tiene todo todos tu tus un una uno unos vosotros y ya yo""".split()),
    "it": set("""a ad al alla alle allo anche avere che chi ci come con contro cui da dal dalla dei del della delle dello di dove e ed era essere
        fra gli ha hanno ho i il in io la le lei lo loro lui ma me mi mia mie miei molto ne nei nel nella nelle no noi non nostra nostri
        o per perché più quale quando quella quello questa questi questo se si sia sono su sua sue suo suoi tra tu tua tue tuo tuoi
        tutti tutto un una uno voi vostra vostri""".split()),
}


def detect_language(words):
    """Langue probable d'un texte d'après la part de mots vides de chaque langue (seuil 8 %) ; None si incertain."""
    ws = [w.lower() for w in words if len(w) >= 2]
    if len(ws) < 20:
        return None
    share = {lang: sum(1 for w in ws if w in sw) / len(ws) for lang, sw in STOPWORDS.items()}
    best = max(share, key=share.get)
    return best if share[best] >= 0.08 else None


def word_regex():
    base = r"[^\W_]" if ARGS.wl_digits else r"[^\W\d_]"
    return re.compile(rf"{base}+(?:[-’']{base}+)*" if ARGS.wl_hyphen else rf"{base}+")


def tokenize(text):
    """Mots d'un texte (lettres Unicode ; --wl-digits, --wl-hyphen, --wl-lower, --wl-min/--wl-maxlen)."""
    lo = ARGS.wl_min if ARGS.wl_min is not None else 3
    found = word_regex().findall(text)
    words = [w for w in found if lo <= len(w) <= ARGS.wl_maxlen]
    stop = ARGS._wl_stop
    if ARGS._wl_auto:                                            # langue détectée PAR SOURCE
        lang = detect_language(found)
        stop = STOPWORDS[lang] if lang else set()
    if stop:
        words = [w for w in words if w.lower() not in stop]
    return [w.lower() for w in words] if ARGS.wl_lower else words


def list_like(lines):
    """Vrai si le texte ressemble à une liste (une entrée courte par ligne) plutôt qu'à de la prose."""
    ls = [l.strip() for l in lines if l.strip()]
    if len(ls) < 5:
        return False
    lens = sorted(len(l) for l in ls)
    short = sum(1 for l in ls if len(l.split()) <= 2) / len(ls)
    return lens[len(lens) // 2] <= 40 and short >= 0.7


def wl_fetch(url):
    """-> (kind, pieces, links) ; kind : plain | text ; pieces : lignes/segments de texte ; links : liens à suivre."""
    local = url == "-" or os.path.isfile(url)
    dk = doc_kind(url)
    if dk and url != "-":
        if os.path.isfile(url):
            with open(url, "rb") as f:
                data = f.read(DOC_MAX)
        else:
            data, _, _ = fetch(url, binary=True, max_bytes=DOC_MAX)
        return "text", extract_doc_text(data, dk).splitlines(), []
    if ARGS.render and not local:
        body, final, ctype = render_or_fetch(url)
    else:
        (body, ctype), final = read_source(url), url
    sk = None if local else sniff_doc_kind(body, ctype)
    if sk:
        data, _, _ = fetch(to_raw_url(url), binary=True, max_bytes=DOC_MAX)
        return "text", extract_doc_text(data, sk).splitlines(), []
    root = XML_ROOT_RE.match(body[:3000])
    if root:
        if root.group(1).lower() in ("urlset", "sitemapindex"):
            return "plain", [l["url"] for l in sitemap_page(url, direct=True)["links"]], []
        pg = parse_feed(body, url)
        return "text", [f"{e['title']} {e['summary']}" for e in pg["entries"]], []
    if host(url) in HTML_PASTE_SITES or looks_html(body, ctype):
        p = PageParser(final)
        p.feed(body)
        return "text", (p.main_pieces() if ARGS.main else p.text), [l["url"] for l in p.links if link_ok(l, final)]
    return "plain", body.splitlines(), []


def wl_entries(kind, pieces):
    mode = ARGS.wl_mode
    if mode == "auto":
        mode = "lines" if (kind == "plain" and list_like(pieces)) else "words"
    if mode == "lines":
        lo = ARGS.wl_min if ARGS.wl_min is not None else 1
        out = []
        for l in pieces:
            l = l.strip()
            if not l or (ARGS.strip_comments and l.startswith(("#", ";", "//"))) or not lo <= len(l) <= 10_000:
                continue
            out.append(l.lower() if ARGS.wl_lower else l)
    else:
        out = tokenize("\n".join(pieces))
    return [e for e in out if text_ok(e)]


BINARY_EXT_RE = re.compile(r"\.(jpe?g|png|gif|svg|webp|ico|css|js|mp[34]|avi|mkv|zip|gz|tar|7z|rar|exe|iso|dmg)$", re.I)


def wl_page(url, agg, live):
    live.src(url, "run")
    remote = not (url == "-" or os.path.isfile(url))
    try:
        if remote and not allowed_by_robots(url):
            live.src(url, "skip")
            return {"url": url, "kind": "skip", "entries": 0, "links": [], "error": None}
        kind, pieces, links = wl_fetch(url)
        entries = wl_entries(kind, pieces)
        agg.add(entries, url)
        live.src(url, "ok", len(entries))
        return {"url": url, "kind": kind, "entries": len(entries), "links": links, "error": None}
    except Exception as e:
        live.src(url, "err")
        info(f"[!] {url} : {e}")
        return {"url": url, "kind": "error", "entries": 0, "links": [], "error": str(e)}


def wl_crawl(urls, agg, live):
    """Lecture des sources, avec crawl (--depth, --max-pages, même domaine sauf --any-domain)."""
    seen, report, level, depth = set(), [], uniq(urls), 0
    while level:
        batch = [u for u in level if u not in seen][: max(0, ARGS.max_pages - len(seen))]
        if not batch:
            break
        seen.update(batch)
        live.total = max(live.total, len(seen))
        with ThreadPoolExecutor(max_workers=ARGS.threads) as ex:
            got = list(ex.map(lambda u: wl_page(u, agg, live), batch))
        report += got
        if depth >= ARGS.depth:
            break
        nxt = []
        for g in got:
            for l in g["links"]:
                if (ARGS.any_domain or host(l) == host(g["url"])) and not BINARY_EXT_RE.search(urllib.parse.urlparse(l).path):
                    nxt.append(l.split("#")[0])
        level, depth = uniq(nxt), depth + 1
    return report


def wl_sorted(counter):
    items = [(w, c) for w, c in counter.items() if c >= ARGS.wl_min_count]
    if ARGS.wl_sort == "freq":
        items.sort(key=lambda x: (-x[1], x[0]))
    elif ARGS.wl_sort == "alpha":
        items.sort(key=lambda x: x[0].lower())
    return items


def slugify(text, n=40):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"^https?://(www\.)?", "", text.lower())).strip("-")[:n] or "wordlist"


def free_space(path):
    p = os.path.abspath(path)
    while not os.path.exists(p):
        p = os.path.dirname(p)
    return shutil.disk_usage(p).free


def wl_write(items, agg, report, label):
    """Écrit wordlist.txt (+ un .txt par source avec --wl-split, + manifest.json). Refuse si le disque est trop plein."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = ARGS.wl_dir or (None if (ARGS.output and not ARGS.wl_split)
                              else os.path.expanduser(f"~/wordlists/scrapaud/{slugify(label)}_{stamp}"))
    merged = ARGS.output or os.path.join(out_dir, "wordlist.txt")
    size = sum(len(w.encode("utf-8")) + 1 for w, _ in items)
    need = size * (2 if ARGS.wl_split else 1) + 100 * 1024 * 1024        # marge : le home est presque plein
    where = out_dir or os.path.dirname(os.path.abspath(merged))
    if free_space(where) < need:
        raise SystemExit(f"[!] espace disque insuffisant pour écrire la wordlist ({size // 1024} Ko + 100 Mo de marge)")
    os.makedirs(os.path.dirname(os.path.abspath(merged)), exist_ok=True)
    files = [merged]
    with open(merged, "w", encoding="utf-8") as f:
        f.write("\n".join(w for w, _ in items) + "\n")
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        if ARGS.wl_split and agg.per_source:
            for i, (src, ctr) in enumerate(agg.per_source.items(), 1):
                part = wl_sorted(ctr)
                if not part:
                    continue
                path = os.path.join(out_dir, f"{i:02d}_{slugify(src, 50)}.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(w for w, _ in part) + "\n")
                files.append(path)
        manifest = {"créé": datetime.datetime.now().isoformat(timespec="seconds"), "sujet": label,
                    "uniques": len(items), "vus": agg.total, "fichiers": [os.path.basename(x) for x in files],
                    "options": {"mode": ARGS.wl_mode, "tri": ARGS.wl_sort, "min": ARGS.wl_min, "maxlen": ARGS.wl_maxlen,
                                "lower": ARGS.wl_lower, "digits": ARGS.wl_digits, "hyphen": ARGS.wl_hyphen,
                                "depth": ARGS.depth},
                    "sources": [{k: r[k] for k in ("url", "kind", "entries", "error")} for r in report],
                    "top": items[:20] if ARGS.wl_sort == "freq" else agg.top(20)}
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        files.append(os.path.join(out_dir, "manifest.json"))
    return files


def run_wordlist(urls, label):
    agg = WordAgg(keep_sources=ARGS.wl_split)
    live = LiveView("wordlist en direct", agg, total=len(urls), show_top=(ARGS.wl_mode != "lines"))
    live.start()
    try:
        report = wl_crawl(urls, agg, live)
    finally:
        live.stop()
    items = wl_sorted(agg.counter)[: ARGS.wl_limit]
    if not items:
        info("[!] aucune entrée extraite (sources vides ou filtres trop stricts)")
        return 1
    if ARGS.interactive:
        idx = run_selector([f"{w}  ×{c}" if c > 1 else w for w, c in items], None, "all",
                           f"{len(items)} entrées — décoche ce que tu ne veux pas dans la wordlist")
        if idx is None:
            _cancelled()
        items = [items[i] for i in idx]
    files = wl_write(items, agg, report, label)
    ok = sum(1 for r in report if not r["error"])
    info(green(f"[*] {len(items)} entrées uniques ({agg.total} vues) depuis {ok}/{len(report)} sources"))
    if ARGS.json:
        print(json.dumps({"uniques": len(items), "vus": agg.total, "fichiers": files,
                          "sources": [{k: r[k] for k in ("url", "kind", "entries", "error")} for r in report]},
                         ensure_ascii=False, indent=2))
    else:
        print("\n".join(files))
    return 0


# ------------------------------------------------------------ autocomplétion bash
def completion_script(ap):
    """Script bash généré depuis le parseur réel (jamais désynchronisé des options)."""
    values = {
        "-e": ["auto", "all", *ENGINES], "--engine": ["auto", "all", *ENGINES],
        "-x": [*EXTRACTS, "all"], "--extract": [*EXTRACTS, "all"],
        "--category": ["general", "images", "news", "videos", "music", "files", "it", "science", "social", "map"],
        "--paste-sites": ["all", *PASTE_DOMAINS], "--archive-syntax": ["all", *SYNTAXES],
        "--wl-stopwords": list(STOPWORDS), "--from": ["auto", "pre", "li", "table", "text"],
        "--completion": ["bash"],
    }
    files = {"-o", "--output", "-f", "--file", "-Q", "--queries-file", "--config", "--wl-dir"}
    opts = []
    for a in ap._actions:
        opts += a.option_strings
        if a.choices and a.option_strings:
            for o in a.option_strings:
                values.setdefault(o, list(map(str, a.choices)))
    lines = ["# scrapaud — autocomplétion bash (générée par `scrapaud --completion bash`)", "_scrapaud() {",
             '    local cur="${COMP_WORDS[COMP_CWORD]}" prev="${COMP_WORDS[COMP_CWORD-1]}"',
             '    case "$prev" in']
    for o, vs in sorted(values.items()):
        lines.append(f'        {o}) COMPREPLY=($(compgen -W "{" ".join(vs)}" -- "$cur")); return ;;')
    lines.append(f'        {"|".join(sorted(files))}) COMPREPLY=($(compgen -f -- "$cur")); return ;;')
    lines += ["    esac", f'    COMPREPLY=($(compgen -W "{" ".join(sorted(set(opts)))}" -- "$cur"))', "}",
              "complete -o filenames -F _scrapaud scrapaud scrapaud.py", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- diagnostic
OK, WARN, ERR, NOTE = "ok", "warn", "err", "info"


def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)


def _tor_port():
    ph, _, pp = (ARGS.tor_proxy or "127.0.0.1:9050").rpartition(":")
    return (ph or "127.0.0.1"), int(pp)


def doctor_local():
    """Contrôles hors ligne et instantanés -> [(état, nom, détail)]."""
    out = []
    add = lambda st, name, detail="": out.append((st, name, detail))
    v = sys.version.split()[0]
    add(OK if sys.version_info >= (3, 11) else ERR, "Python", v if sys.version_info >= (3, 11) else f"{v} (3.11+ requis : tomllib)")
    pt = shutil.which("pdftotext")
    if pt:
        add(OK, "Lecture PDF (pdftotext)", (_run([pt, "-v"])[1].splitlines() or ["présent"])[0])
    else:
        add(WARN, "Lecture PDF (pdftotext)", "absent : les PDF ne seront pas lus (paquet poppler-utils)")
    try:
        add(OK, "Rendu JavaScript (--render)", " ".join(find_browser()))
    except ValueError:
        add(WARN, "Rendu JavaScript (--render)", "aucun Chromium/Chrome trouvé : --render indisponible")
    if ARGS.searx:
        try:
            fetch(ARGS.searx.rstrip("/") + "/healthz", retries=0)
            svc = ""
            if shutil.which("systemctl"):
                svc = " · service " + (_run(["systemctl", "--user", "is-active", "searxng"])[1] or "inconnu")
            add(OK, "SearXNG", f"{ARGS.searx} répond{svc}")
        except Exception as e:
            add(ERR, "SearXNG", f"{ARGS.searx} injoignable : {e}")
    else:
        add(WARN, "SearXNG", "aucune instance (--searx URL) : recherche via Bing/DuckDuckGo, plus fragile")
    ph, pp = _tor_port()
    try:
        socket.create_connection((ph, pp), timeout=1.5).close()
        add(OK, "Tor (SOCKS5)", f"{ph}:{pp} ouvert : .onion et --tor utilisables")
    except OSError:
        add(WARN, "Tor (SOCKS5)", f"{ph}:{pp} fermé : .onion et --tor indisponibles")
    home = os.path.expanduser("~")
    du = shutil.disk_usage(home)
    used = 100 * (du.total - du.free) / du.total
    st = ERR if du.free < 500 * 2**20 else (WARN if du.free < 5 * 2**30 or used >= 95 else OK)
    add(st, "Disque (home)", f"{du.free / 2**30:.1f} Go libres ({used:.0f} % utilisé)"
        + (" : les wordlists refuseront d'écrire sous 100 Mo de marge" if st == ERR else (" : à surveiller" if st == WARN else "")))
    files = glob.glob(os.path.join(CACHE_DIR, "*.json.gz"))
    size = sum(os.path.getsize(f) for f in files if os.path.exists(f))
    add(OK if size <= CACHE_MAX * 1.1 else WARN, "Cache", f"{size / 1024:.0f} Ko · {len(files)} entrées · max {CACHE_MAX // 2**20} Mo · TTL {ARGS.cache_ttl}s")
    cfg_path = os.environ.get("SCRAPAUD_CONFIG") or os.path.expanduser("~/.config/scrapaud/config.toml")
    if ARGS.config:
        cfg_path = ARGS.config
    if not os.path.exists(cfg_path):
        add(NOTE, "Configuration", f"{cfg_path} absent : valeurs par défaut")
    else:
        try:
            with open(cfg_path, "rb") as f:
                cfg = tomllib.load(f)
            valid = {k.replace("_", "-") for k in vars(ARGS) if not k.startswith("_")}
            unknown = [k for k in cfg if k.replace("_", "-") not in valid]
            add(WARN if unknown else OK, "Configuration", f"{cfg_path} : {len(cfg)} clé(s)"
                + (f" · inconnues : {', '.join(unknown)}" if unknown else ""))
        except (OSError, tomllib.TOMLDecodeError) as e:
            add(ERR, "Configuration", f"{cfg_path} illisible : {e}")
    add(NOTE, "Filtre réseau privé", "DÉSACTIVÉ (--allow-private)" if ARGS.allow_private else "actif (127.x, 10.x, 192.168.x, 169.254.x, Tailscale bloqués)")
    return out


def probe_engines(limit=30):
    """Une requête réelle par moteur, en parallèle et sans cache. Un moteur qui ne répond pas dans `limit` secondes
    est signalé « pas de réponse » (threads daemon : on n'attend pas les retardataires)."""
    def one(name):
        q = "example.com" if name in ("wayback", "crtsh") else "test"
        t0 = time.time()
        try:
            r = ENGINES[name](q, 1)
            return (OK, f"Moteur {name}", f"{len(r)} résultats · {time.time() - t0:.1f}s") if r else \
                   (WARN, f"Moteur {name}", "aucun résultat (bloqué, vide ou en panne)")
        except urllib.error.HTTPError as e:
            return WARN, f"Moteur {name}", f"HTTP {e.code} (limité ou bloqué)"
        except Exception as e:
            return WARN, f"Moteur {name}", str(e)[:90]
    names = [n for n in ENGINES if n != "searxng" or ARGS.searx]
    results = {}
    threads = [threading.Thread(target=lambda n=n: results.__setitem__(n, one(n)), daemon=True) for n in names]
    for th in threads:
        th.start()
    deadline = time.time() + limit
    for th in threads:
        th.join(max(0.0, deadline - time.time()))
    return [results.get(n, (WARN, f"Moteur {n}", f"pas de réponse en {limit} s")) for n in names]


def render_selftest():
    cmd = find_browser() + ["--headless=new", "--disable-gpu", "--no-first-run", "--user-data-dir=" + os.path.join(
        tempfile.gettempdir(), f"scrapaud-doctor-{os.getpid()}"), "--virtual-time-budget=3000", "--dump-dom",
        "data:text/html,<body><script>document.body.textContent='rendu-js-ok'</script>"]
    t0 = time.time()
    try:
        rc, out = _run(cmd, timeout=60)
    finally:
        shutil.rmtree(os.path.join(tempfile.gettempdir(), f"scrapaud-doctor-{os.getpid()}"), ignore_errors=True)
    return ("rendu-js-ok" in out), time.time() - t0


def doctor_deep():
    """Contrôles réseau (trafic externe) -> [(état, nom, détail)]."""
    out = []
    add = lambda st, name, detail="": out.append((st, name, detail))
    t0 = time.time()
    try:
        fetch("https://example.com", retries=0)
        add(OK, "Internet (HTTPS direct)", f"example.com en {time.time() - t0:.1f}s")
    except Exception as e:
        add(ERR, "Internet (HTTPS direct)", str(e)[:100])
    try:
        socket.create_connection(_tor_port(), timeout=1.5).close()
        old, ARGS.tor = ARGS.tor, True
        try:
            txt, _, _ = fetch("https://check.torproject.org/api/ip", retries=0)
        finally:
            ARGS.tor = old
        info_ = json.loads(txt)
        add(OK if info_.get("IsTor") else ERR, "Tor (trafic réel)", f"IsTor={info_.get('IsTor')} · IP de sortie {info_.get('IP')}")
    except OSError:
        add(WARN, "Tor (trafic réel)", "port fermé : non testé")
    except Exception as e:
        add(ERR, "Tor (trafic réel)", str(e)[:100])
    if ARGS.searx:
        try:
            txt, _, _ = fetch(ARGS.searx.rstrip("/") + "/search?" + urllib.parse.urlencode({"q": "test", "format": "json"}), retries=0)
            d = json.loads(txt)
            bad = ", ".join(f"{e[0]} ({e[1]})" for e in d.get("unresponsive_engines", []))
            add(OK if d.get("results") else WARN, "SearXNG (recherche JSON)", f"{len(d.get('results', []))} résultats"
                + (f" · en échec : {bad}" if bad else ""))
        except urllib.error.HTTPError as e:
            add(ERR, "SearXNG (recherche JSON)", "format json refusé (403) : ajoute `json` à search.formats dans settings.yml" if e.code == 403 else f"HTTP {e.code}")
        except Exception as e:
            add(ERR, "SearXNG (recherche JSON)", str(e)[:100])
    try:
        find_browser()
        ok, dt = render_selftest()
        add(OK if ok else ERR, "Rendu JavaScript (test réel)", f"JavaScript exécuté en {dt:.1f}s" if ok else "le navigateur n'a pas rendu la page de test")
    except ValueError:
        pass
    info("[*] sondage des moteurs (une requête chacun, en parallèle)…")
    out += probe_engines()
    return out


def run_doctor():
    setup_security([])                       # SearXNG local = hôte de confiance
    ARGS.no_cache = True
    checks = doctor_local() + (doctor_deep() if ARGS.deep else [])
    if ARGS.json:
        print(json.dumps([{"état": st, "nom": n, "détail": d} for st, n, d in checks], ensure_ascii=False, indent=2))
    else:
        tty = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        sym = {OK: ("✔", "\033[92m"), WARN: ("⚠", "\033[33m"), ERR: ("✘", "\033[91m"), NOTE: ("·", "\033[32m")}
        print(green(f"\n  scrapaud v{VERSION} — diagnostic" + (" approfondi" if ARGS.deep else "")) + "\n")
        w = max(len(n) for _, n, _ in checks)
        for st, n, d in checks:
            mark, col = sym[st]
            print(f"  {(col + mark + chr(27) + '[0m') if tty else mark} {n:<{w}}  {d}")
        c = collections.Counter(st for st, _, _ in checks)
        print(f"\n  {c[OK]} ok · {c[WARN]} avertissement(s) · {c[ERR]} erreur(s)"
              + ("" if ARGS.deep else "   (--deep : Internet, Tor réel, SearXNG, rendu JS, sondage des moteurs)") + "\n")
    return 1 if any(st == ERR for st, _, _ in checks) else 0


# ------------------------------------------------- sélection interactive (-i)
class Selector:
    """État d'une liste à cocher (sans aucun affichage : testable seul)."""

    def __init__(self, labels, details=None, selected=None):
        self.labels = list(labels)
        n = len(self.labels)
        self.details = list(details) if details else [""] * n
        self.sel = set(range(n)) if selected == "all" else set(selected or [])
        self.filter = ""
        self.visible = list(range(n))
        self.cur = 0
        self.top = 0

    def set_filter(self, text):
        keep = self.visible[self.cur] if self.visible else None
        self.filter = text
        t = text.lower()
        self.visible = [i for i in range(len(self.labels))
                        if not t or t in self.labels[i].lower() or t in self.details[i].lower()]
        self.cur = self.visible.index(keep) if keep in self.visible else 0
        self.top = 0

    def move(self, delta):
        if self.visible:
            self.cur = max(0, min(len(self.visible) - 1, self.cur + delta))

    def home(self):
        self.cur = 0

    def end(self):
        self.cur = max(0, len(self.visible) - 1)

    def toggle(self):
        if self.visible:
            self.sel ^= {self.visible[self.cur]}

    def select_visible(self, on=True):
        (self.sel.update if on else self.sel.difference_update)(self.visible)

    def invert_visible(self):
        self.sel ^= set(self.visible)

    def result(self):
        return sorted(self.sel)

    def parse(self, text):
        """Saisie en mode texte : `a` tout, `n` rien, `/mot` ajoute les correspondances, `1,3-5` remplace la sélection."""
        t, n = text.strip(), len(self.labels)
        if t.lower() == "a":
            self.sel = set(range(n))
        elif t.lower() == "n":
            self.sel = set()
        elif t.startswith("/"):
            needle = t[1:].lower()
            self.sel |= {i for i in range(n) if needle in self.labels[i].lower() or needle in self.details[i].lower()}
        else:
            new = set()
            for part in t.replace(" ", "").split(","):
                if not part:
                    continue
                m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
                if not m:
                    raise ValueError(f"saisie invalide : {part}")
                a, b = int(m.group(1)), int(m.group(2) or m.group(1))
                if a < 1 or b > n or a > b:
                    raise ValueError(f"hors limites : {part} (1-{n})")
                new |= set(range(a - 1, b))
            self.sel = new


@contextlib.contextmanager
def tty_io():
    """Branche stdin/stdout sur /dev/tty le temps de l'interface : les résultats restent pipeables sur stdout."""
    try:
        tty = os.open("/dev/tty", os.O_RDWR)
    except OSError:
        raise SystemExit("[!] --interactive nécessite un terminal (aucun /dev/tty disponible)")
    sys.stdout.flush()
    saved = os.dup(0), os.dup(1)
    os.dup2(tty, 0)
    os.dup2(tty, 1)
    try:
        yield
    finally:
        try:
            sys.stdout.flush()
        except OSError:
            pass
        os.dup2(saved[0], 0)
        os.dup2(saved[1], 1)
        for fd in (*saved, tty):
            os.close(fd)


HINTS = [   # de la plus complète à la plus courte : on prend la plus longue qui tient dans la largeur
    " ↑↓ jk : naviguer · espace : cocher · a : tout · n : rien · i : inverser · / : filtrer · Entrée : valider · q : annuler",
    " ↑↓ naviguer · espace cocher · a tout · n rien · / filtre · Entrée valider · q annuler",
    " espace cocher · a tout · / filtre · Entrée valider · q annuler",
    " espace · Entrée valider · q annuler",
    " Entrée = valider · q = annuler",
]
FILTER_HINTS = [" filtre : {buf}_   (Entrée : garder · Échap : effacer)", " filtre : {buf}_  (Entrée garder · Échap effacer)", " filtre : {buf}_ · Entrée · Échap"]


def fit(text, width):
    """Tronque avec « … » pour tenir dans `width` colonnes."""
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def pick_hint(hints, width, **kw):
    """Aide la plus complète qui tient dans `width` ; à défaut, la plus courte tronquée."""
    for h in hints:
        h = h.format(**kw) if kw else h
        if len(h) <= width:
            return h
    return fit(hints[-1].format(**kw) if kw else hints[-1], width)


def _curses_ui(stdscr, sel, title):
    curses.curs_set(0)
    green = 0
    try:
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        green = curses.color_pair(1)
    except curses.error:
        pass
    stdscr.keypad(True)
    mode, buf = "nav", ""

    def put(y, x, text, attr=0):
        h, w = stdscr.getmaxyx()
        if 0 <= y < h and x < w - 1:
            try:
                stdscr.addnstr(y, x, text, w - x - 1, attr)
            except curses.error:
                pass

    while True:
        h, w = stdscr.getmaxyx()
        list_h = max(1, h - 5)
        if sel.cur < sel.top:
            sel.top = sel.cur
        if sel.cur >= sel.top + list_h:
            sel.top = sel.cur - list_h + 1
        stdscr.erase()
        put(0, 0, fit(f" {title}", w - 1), curses.A_BOLD | green)
        put(1, 0, f" {len(sel.sel)}/{len(sel.labels)} cochés · {len(sel.visible)} affichés"
                  + (f" · filtre : {sel.filter}" if sel.filter else ""), green)
        for row in range(list_h):
            idx = sel.top + row
            if idx >= len(sel.visible):
                break
            i = sel.visible[idx]
            mark = "[x]" if i in sel.sel else "[ ]"
            attr = curses.A_REVERSE if idx == sel.cur else (green if i in sel.sel else 0)
            put(2 + row, 0, fit(f" {mark} {i + 1:>4}. {sel.labels[i]}", w - 1), attr)
        if sel.visible:
            for k, line in enumerate(sel.details[sel.visible[sel.cur]].splitlines()[:2]):
                put(h - 3 + k, 2, fit(line, w - 3), curses.A_DIM)
        if mode == "filter":
            put(h - 1, 0, pick_hint(FILTER_HINTS, w - 1, buf=buf), green)
        else:
            put(h - 1, 0, pick_hint(HINTS, w - 1), green)
        stdscr.refresh()
        try:
            key = stdscr.get_wch()
        except curses.error:
            continue
        if key == curses.KEY_RESIZE:
            continue
        if mode == "filter":
            if key in ("\n", "\r", curses.KEY_ENTER):
                mode = "nav"
            elif key == "\x1b":
                buf = ""
                sel.set_filter("")
                mode = "nav"
            elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                buf = buf[:-1]
                sel.set_filter(buf)
            elif isinstance(key, str) and key.isprintable():
                buf += key
                sel.set_filter(buf)
            continue
        if key in (curses.KEY_UP, "k"):
            sel.move(-1)
        elif key in (curses.KEY_DOWN, "j"):
            sel.move(1)
        elif key == curses.KEY_PPAGE:
            sel.move(-list_h)
        elif key == curses.KEY_NPAGE:
            sel.move(list_h)
        elif key in (curses.KEY_HOME, "g"):
            sel.home()
        elif key in (curses.KEY_END, "G"):
            sel.end()
        elif key == " ":
            sel.toggle()
            sel.move(1)
        elif key == "a":
            sel.select_visible(True)
        elif key == "n":
            sel.select_visible(False)
        elif key == "i":
            sel.invert_visible()
        elif key == "/":
            mode, buf = "filter", sel.filter
        elif key in ("\n", "\r", curses.KEY_ENTER):
            return "ok"
        elif key in ("q", "\x1b"):
            return "cancel"


def plain_ui(sel, title, inp=None, out=None):
    """Mode texte (sans curses) : liste numérotée + saisie de la sélection."""
    close = []
    if inp is None:
        try:   # un tty n'est pas « seekable » : deux descripteurs distincts (lecture / écriture), pas "r+"
            inp = open("/dev/tty", "r", encoding="utf-8", errors="replace")
            out = open("/dev/tty", "w", encoding="utf-8", errors="replace")
        except OSError:
            raise SystemExit("[!] --interactive nécessite un terminal (aucun /dev/tty disponible)")
        close += [inp, out]
    try:
        out.write(f"\n{title}\n")
        shown = min(len(sel.labels), 300)
        for i in range(shown):
            out.write(f"{'*' if i in sel.sel else ' '} {i + 1:>4}. {sel.labels[i][:110]}\n")
        if len(sel.labels) > shown:
            out.write(f"  … {len(sel.labels) - shown} autres (utilise /texte pour les cibler)\n")
        while True:
            out.write("Sélection [1,3-5 · a=tout · n=rien · /texte · Entrée=valider · q=annuler] : ")
            out.flush()
            line = inp.readline()
            if line == "" or line.strip().lower() == "q":
                return None
            if not line.strip():
                return sel.result()
            try:
                sel.parse(line)
                out.write(f"→ {len(sel.sel)} coché(s)\n")
            except ValueError as e:
                out.write(f"[!] {e}\n")
    finally:
        for f in close:
            f.close()


def run_selector(labels, details=None, selected=None, title="", plain=None):
    """Affiche la sélection ; -> liste d'indices cochés, ou None si annulé."""
    sel = Selector(labels, details, selected)
    if not sel.labels:
        return []
    use_plain = ARGS.plain if plain is None else plain
    if not use_plain and curses is not None and os.environ.get("TERM", "dumb") != "dumb":
        try:
            os.environ.setdefault("ESCDELAY", "25")
            with tty_io():
                res = curses.wrapper(_curses_ui, sel, title)
            return sel.result() if res == "ok" else None
        except curses.error as e:
            info(f"[!] interface curses indisponible ({e}) : mode texte")
    return plain_ui(sel, title)


def _cancelled():
    info("[*] annulé")
    raise SystemExit(130)


def pick_results(res, q):
    idx = run_selector([f"{r['title'] or r['url']}  [{r.get('engine', '')}]" for r in res],
                       [f"{r['url']}\n{r.get('snippet', '')}" for r in res], None,
                       f"« {q} » — coche les résultats à garder")
    if idx is None:
        _cancelled()
    if not idx:
        info("[!] aucun résultat coché")
    return [res[i] for i in idx]


def pick_entries(tl):
    items = tl["items"]
    idx = run_selector([i["line"] for i in items], [i["source"] for i in items], "all",
                       f"{len(items)} entrées — décoche le bruit (tout est coché au départ)")
    if idx is None:
        _cancelled()
    kept = [items[i] for i in idx]
    return dict(tl, items=kept, count=len(kept))


def pick_links(pages):
    rows = [(pg["url"], l) for pg in pages for l in pg.get("links", [])]
    if not rows:
        return pages
    idx = run_selector([f"{(l['text'] or l['url'])[:70]}  →  {l['url']}" for _, l in rows], [u for u, _ in rows],
                       None, f"{len(rows)} liens — coche ceux à garder")
    if idx is None:
        _cancelled()
    chosen = [rows[i][1] for i in idx]
    return [{"url": "sélection", "title": f"{len(chosen)} liens choisis", "description": "", "links": chosen}]


# ----------------------------------------------- exports sûrs (contenu non fiable)
def csv_safe(v):
    """Neutralise l'injection de formules : une cellule commençant par = + - @ (ou tab/retour) reçoit une apostrophe.
    --csv-raw pour désactiver (ex. valeurs négatives destinées à un traitement machine)."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r", "\n") and not ARGS.csv_raw:
        return "'" + v
    return v


class SafeCsv:
    def __init__(self, writer):
        self.w = writer

    def writerow(self, row):
        self.w.writerow([csv_safe(c) for c in row])

    def writerows(self, rows):
        for r in rows:
            self.writerow(r)


def md_text(t):
    """Échappe le Markdown et le HTML brut dans un texte venant du web."""
    return re.sub(r"([\\\[\]<>`*_|])", r"\\\1", str(t))


def md_link(text, url):
    """Lien Markdown sûr : http(s)/mailto seulement, parenthèses et espaces encodés ; sinon simple texte."""
    if not re.match(r"(?i)(https?://|mailto:)", url):
        return md_text(text or url)
    safe = url.replace("(", "%28").replace(")", "%29").replace(" ", "%20").replace("<", "%3C").replace(">", "%3E")
    return f"[{md_text(text or url)}]({safe})"


def html_link(text, url):
    text = ihtml.escape(text or url)
    if not re.match(r"(?i)(https?://|mailto:)", url):
        return text
    return f'<a href="{ihtml.escape(url)}" rel="noopener noreferrer nofollow">{text}</a>'


# ------------------------------------------------------------------- sorties
def save(path, data):
    ext = os.path.splitext(path)[1].lower()
    searches, pages = data["searches"], data["pages"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        if ext == ".json":
            json.dump(data, f, ensure_ascii=False, indent=2)
        elif ext == ".csv":
            w = SafeCsv(csv.writer(f))
            w.writerow(["source", "type", "text", "url"])
            for r in searches:
                w.writerow([r["query"], "result", r["title"], r["url"]])
            for pg in pages:
                if pg.get("type") == "paste":
                    w.writerow([pg["site"], "paste", pg["title"], pg["url"]])
                    for m in pg.get("matches", []):
                        w.writerow([pg["url"], "match", m, ""])
                for l in pg.get("links", []):
                    w.writerow([pg["url"], "link", l["text"], l["url"]])
                for i in pg.get("items", []):
                    w.writerow([pg["url"], "item", i, ""])
                for i in pg.get("images", []):
                    w.writerow([pg["url"], "image", i["alt"], i["url"]])
                for e in pg.get("emails", []):
                    w.writerow([pg["url"], "email", e, ""])
        elif ext in (".md", ".html", ".htm"):
            lines = []
            for r in searches:
                lines.append((r["title"], r["url"], r["snippet"]))
            for pg in pages:
                if pg.get("type") == "paste":
                    lines.append((pg["title"] or pg["url"], pg["url"], f"[{pg['site']}]"))
                for l in pg.get("links", []):
                    lines.append((l["text"] or l["url"], l["url"], ""))
            if ext == ".md":
                f.write("\n".join(f"- {md_link(t, u)} {md_text(s)}".rstrip() for t, u, s in lines) + "\n")
            else:
                rows = "\n".join(f"<li>{html_link(t, u)} {ihtml.escape(s)}</li>" for t, u, s in lines)
                f.write(f"<!doctype html><meta charset=utf-8><title>scrapaud</title><ul>\n{rows}\n</ul>\n")
        else:
            f.write("\n".join(uniq(all_urls(data))) + "\n")
    info(green(f"[+] sauvegardé : {path}"))


def all_urls(data):
    return ([r["url"] for r in data["searches"]]
            + [pg["url"] for pg in data["pages"] if pg.get("type") == "paste"]
            + [l["url"] for pg in data["pages"] for l in pg.get("links", [])])


def display(data):
    if ARGS.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    if ARGS.urls_only:
        print("\n".join(uniq(all_urls(data))))
        return
    n = 0
    for r in data["searches"]:
        n += 1
        print(f"{green(f'{n:>3}.')} {r['title']}  {dgreen('[' + r['engine'] + ']')}\n     {r['url']}")
        if r["snippet"]:
            print(dgreen(f"     {r['snippet'][:160]}"))
    for pg in data["pages"]:
        if pg.get("type") == "paste":
            print(green(f"\n=== [paste] {pg['url']}") + dgreen(f"  {pg['size']} o") + (f"  {pg['title']}" if pg.get("title") else ""))
            shown = pg.get("matches") or (pg.get("content") or "").splitlines()[:12]
            for ln in shown[:25]:
                print(f"  {green('|')} {ln[:200]}")
            for e in pg.get("emails", []):
                print(f"  {green('@')} {e}")
            for l in pg.get("links", []):
                print(f"  {green('→')} {l['url']}")
            if pg.get("file"):
                print(f"  {green('⤓')} enregistré : {pg['file']}")
            continue
        print(green(f"\n=== {pg['url']}") + (f"  {pg['title']}" if pg.get("title") else ""))
        if pg.get("description"):
            print(dgreen(f"    {pg['description'][:200]}"))
        if pg.get("hint"):
            print(dgreen(f"    ⚠ {pg['hint']}"))
        for fd in pg.get("feeds", []):
            print(f"  {green('⌁ flux')} {fd}")
        for h in pg.get("headings", []):
            print(f"  {green('#' * h['level'])} {h['text']}")
        for l in pg.get("links", []):
            print(f"  {green('→')} {l['text'][:55]:<55} {l['url']}")
        for i in pg.get("items", []):
            print(f"  {green('•')} {i[:140]}")
        for t in pg.get("tables", []):
            print(green(f"  [table {len(t)} lignes]"))
            for row in t[:15]:
                print("    " + " | ".join(row))
        for i in pg.get("images", []):
            print(f"  {green('▣')} {i['alt'][:40]:<40} {i['url']}")
        for e in pg.get("emails", []):
            print(f"  {green('@')} {e}")
        if pg.get("text"):
            print("  " + pg["text"][:800])


# ---------------------------------------------------------------------- main
def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="scrapaud", description="Scraper de listes/liens/données pour n'importe quel sujet.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    s = ap.add_argument_group("recherche (n'importe quel nom / mot-clé / chose)")
    s.add_argument("-q", "--query", action="append", default=[], help="sujet à rechercher (répétable)")
    s.add_argument("-Q", "--queries-file", help="fichier : une recherche par ligne")
    s.add_argument("-e", "--engine", default="auto",
                   help="auto | all | liste parmi " + ",".join(ENGINES) + " (défaut auto = searxng si --searx, puis bing>ddg>wikipedia)")
    s.add_argument("-p", "--pages", type=int, default=1, help="pages de résultats par moteur (défaut 1)")
    s.add_argument("-n", "--limit", type=int, default=30, help="max résultats gardés par recherche (défaut 30)")
    s.add_argument("--searx", default=os.environ.get("SCRAPAUD_SEARX"),
                   help="URL de ton instance SearXNG (ou variable SCRAPAUD_SEARX) ; active le moteur searxng")
    s.add_argument("--category", help="catégorie(s) SearXNG, séparées par des virgules : general images news videos music files it science social map")
    s.add_argument("--since", choices=["day", "week", "month", "year"], help="période des résultats (SearXNG)")
    s.add_argument("--onion", action="store_true", help="deep web : cherche des services .onion (Ahmia) ; les .onion sont lus via Tor")
    s.add_argument("--se-site", default="stackoverflow", help="site StackExchange pour -e stackexchange (défaut stackoverflow)")
    s.add_argument("--no-searx", action="store_true", help="ne pas utiliser l'instance SearXNG locale détectée automatiquement")
    s.add_argument("--searx-engines", help="moteurs SearXNG à interroger, ex google,bing,brave (défaut : ceux de l'instance)")
    s.add_argument("--site", help="restreindre à un domaine (site:...)")
    s.add_argument("--filetype", help="type de fichier (pdf, docx, xlsx...)")
    s.add_argument("--lang", default="fr", help="langue (défaut fr)")
    t = ap.add_argument_group("cibles à scraper")
    t.add_argument("-u", "--url", action="append", default=[], help="URL à scraper (répétable)")
    t.add_argument("-f", "--file", help="fichier : une URL par ligne")
    t.add_argument("--sitemap", action="store_true", help="lister les URLs du sitemap du site (robots.txt, /sitemap.xml, index récursifs)")
    t.add_argument("--sitemap-max", type=int, default=5000, help="max URLs lues dans les sitemaps (défaut 5000)")
    t.add_argument("--follow", action="store_true", help="scraper chaque page résultat de recherche")
    t.add_argument("--depth", type=int, default=0, help="profondeur de crawl (défaut 0)")
    t.add_argument("--max-pages", type=int, default=50, help="max pages scrapées (défaut 50)")
    t.add_argument("--any-domain", action="store_true", help="le crawl peut sortir du domaine d'origine")
    x = ap.add_argument_group("extraction & filtres")
    x.add_argument("-x", "--extract", default="links,items", help="parmi " + ",".join(EXTRACTS) + " ou all (défaut links,items)")
    x.add_argument("--grep", help="regex : ne garder que ce qui matche")
    x.add_argument("--exclude", help="regex : retirer ce qui matche")
    x.add_argument("--ext", action="append", default=[], help="liens finissant par cette extension (répétable : --ext pdf --ext zip)")
    x.add_argument("--domain", action="append", default=[], help="liens dont l'hôte contient ce texte (répétable)")
    x.add_argument("--not-domain", action="append", default=[], help="exclure les liens/résultats dont l'hôte contient ce texte (répétable)")
    x.add_argument("--main", action=argparse.BooleanOptionalAction, default=None,
                   help="ne garder que le contenu principal des pages (sans menus, pieds de page, bandeaux cookies, liens de navigation) "
                        "pour text/links/items, --textlist et --wordlist ; activé par défaut avec --wordlist, --no-main pour l'annuler")
    x.add_argument("--same-domain", action="store_true", help="liens du même domaine seulement")
    x.add_argument("--external", action="store_true", help="liens externes seulement")
    x.add_argument("--max-items", type=int, default=500, help="max éléments de liste par page (défaut 500)")
    r = ap.add_argument_group("rendu, cache, configuration")
    r.add_argument("--render", action="store_true", help="exécuter le JavaScript des pages (Chromium headless, profil jetable) pour les sites dynamiques")
    r.add_argument("--render-wait", type=float, default=8.0, help="secondes de JS simulées par page (défaut 8)")
    r.add_argument("--render-timeout", type=int, default=90, help="délai max d'un rendu en secondes (défaut 90)")
    r.add_argument("--browser", help='commande du navigateur (défaut : chromium/chrome, sinon flatpak org.chromium.Chromium)')
    r.add_argument("--cache-ttl", type=int, default=3600, help="durée du cache disque en secondes, 0 = désactivé (défaut 3600)")
    r.add_argument("--no-cache", action="store_true", help="ignorer le cache pour cette exécution")
    r.add_argument("--clear-cache", action="store_true", help="vider le cache (~/.cache/scrapaud) et quitter")
    r.add_argument("--config", help="fichier TOML de valeurs par défaut (défaut ~/.config/scrapaud/config.toml)")
    r.add_argument("--version", action="version", version=f"scrapaud {VERSION}")
    r.add_argument("--completion", choices=["bash"], help="affiche le script d'autocomplétion (ex. scrapaud --completion bash > ~/.local/share/bash-completion/completions/scrapaud)")
    r.add_argument("--doctor", action="store_true", help="diagnostic de l'installation (SearXNG, Tor, pdftotext, Chromium, disque, cache, config)")
    r.add_argument("--deep", action="store_true", help="avec --doctor : tests réseau réels (Internet, Tor, SearXNG, rendu JS, un sondage par moteur)")
    n = ap.add_argument_group("réseau")
    n.add_argument("-t", "--threads", type=int, default=5, help="threads de scraping (défaut 5)")
    n.add_argument("--delay", type=float, default=0.5, help="pause entre requêtes (défaut 0.5s)")
    n.add_argument("--timeout", type=float, default=15)
    n.add_argument("--retries", type=int, default=2)
    n.add_argument("--max-bytes", type=int, default=5_000_000, help="taille max téléchargée par page")
    n.add_argument("--tor", action="store_true", help="passer TOUT le trafic par Tor (les .onion y passent toujours)")
    n.add_argument("--tor-proxy", default=os.environ.get("SCRAPAUD_TOR", "127.0.0.1:9050"), help="SOCKS5 de Tor (défaut 127.0.0.1:9050)")
    n.add_argument("--proxy", help="proxy http(s), ex http://127.0.0.1:8080")
    n.add_argument("--user-agent", help="User-Agent fixe (sinon rotation)")
    n.add_argument("-H", "--header", action="append", default=[], help='en-tête perso "Nom: valeur" (répétable) ; -H @fichier = un en-tête par ligne')
    n.add_argument("--cookie-domain", action="append", default=[], help="domaine(s) autorisé(s) à recevoir --cookie/-H (défaut : les hôtes de -u/-f uniquement)")
    n.add_argument("--allow-private", action="store_true", help="autoriser les adresses privées/locales (127.x, 10.x, 192.168.x, 169.254.x, Tailscale) trouvées via recherche, liens ou redirections")
    n.add_argument("--allow-host", action="append", default=[], help="hôte de confiance autorisé même sur réseau privé (répétable)")
    n.add_argument("--cookie", help="cookies d'une session que TU as ouverte dans ton navigateur (ex \"cf_clearance=...\"). "
                   "Pour ne pas les laisser dans `ps` / l'historique : --cookie @fichier (chmod 600) ou variable SCRAPAUD_COOKIE")
    n.add_argument("--robots", action=argparse.BooleanOptionalAction, default=None,
                   help="robots.txt : par défaut (auto) respecté pour les pages DÉCOUVERTES (liens suivis, résultats de recherche) et pas pour "
                        "les URLs que tu donnes (-u/-f) ; --robots = toujours, --no-robots = jamais")
    tx = ap.add_argument_group("listes de texte (wordlists, IP, domaines... une entrée par ligne)")
    tx.add_argument("--textlist", action="store_true", help="mode liste : extrait les entrées de chaque source (URL, fichier, - = stdin) ; les résultats de -q sont utilisés comme sources")
    tx.add_argument("--as", dest="text_as", default="lines", choices=["lines"] + list(AS_PATTERNS),
                    help="ne garder que ce type de valeurs : " + ",".join(AS_PATTERNS) + " (défaut lines = lignes entières)")
    tx.add_argument("--from", dest="text_from", default="auto", help="pour les pages HTML : auto ou liste parmi pre,li,table,text (défaut auto) ; "
                    "table = la colonne la plus « liste de noms » (hors en-têtes, codes et nombres)")
    tx.add_argument("--strip-comments", action="store_true", help="ignorer les lignes commençant par # ; //")
    tx.add_argument("--min-len", type=int, default=1, help="longueur minimale d'une entrée")
    tx.add_argument("--max-len", type=int, default=10_000, help="longueur maximale d'une entrée")
    tx.add_argument("--sort", action="store_true", help="trier alphabétiquement")
    tx.add_argument("--no-unique", action="store_true", help="garder les doublons")
    tx.add_argument("--max-lines", type=int, default=1_000_000, help="max entrées au total")
    pa = ap.add_argument_group("pastes (pastebin & co, contenus publics)")
    pa.add_argument("--pastes", action="store_true", help="chercher chaque -q sur les sites de paste (pastebin.com, gist, dpaste, rentry...)")
    pa.add_argument("--paste-sites", default="all", help="all ou liste parmi " + ",".join(PASTE_DOMAINS))
    pa.add_argument("--pastebin", action="store_true", help="scanner les pastes publics récents de pastebin.com (/archive)")
    pa.add_argument("--archive-syntax", default="", help="ex python,php ou all : archives pastebin par langage (plus de pastes)")
    pa.add_argument("--gists", action="store_true", help="scanner les derniers gists publics GitHub (API officielle)")
    pa.add_argument("--gist-pages", type=int, default=1, help="pages de 100 gists (défaut 1)")
    pa.add_argument("--watch", type=int, default=0, metavar="SEC", help="rescanner toutes les SEC secondes, n'afficher que les nouveaux")
    pa.add_argument("--paste-max", type=int, default=100, help="max pastes lus par passe (défaut 100)")
    pa.add_argument("--paste-content", type=int, default=20000, help="taille max du contenu gardé par paste, 0 = ne pas garder")
    pa.add_argument("--paste-dir", nargs="?", const="~/pastes/scrapaud", default=None, metavar="DIR",
                    help="enregistrer chaque paste lu dans un fichier .txt (dossier <site>/<date>/, + index.md, droits 700/600) ; sans valeur : ~/pastes/scrapaud")
    pa.add_argument("--titles-only", action="store_true", help="lister les pastes sans télécharger leur contenu")
    w = ap.add_argument_group("wordlists automatiques (--wordlist) et vue temps réel")
    w.add_argument("--wordlist", action="store_true", help="extrait automatiquement une wordlist .txt des sources (-q/-u/-f, --depth pour crawler)")
    w.add_argument("--wl-mode", default="auto", choices=["auto", "words", "lines"],
                   help="words = mots du texte ; lines = une entrée par ligne ; auto = lines pour les fichiers-listes, words pour le reste")
    w.add_argument("--wl-min", type=int, default=None, help="longueur minimale (défaut 3 en mode mots, 1 en mode lignes)")
    w.add_argument("--wl-maxlen", type=int, default=40, help="longueur maximale d'un mot (défaut 40)")
    w.add_argument("--wl-stopwords", help="ignorer les mots vides : auto (langue détectée par source), ou fr, en, de, es, it (liste séparée par des virgules)")
    w.add_argument("--wl-lower", action="store_true", help="tout passer en minuscules")
    w.add_argument("--wl-digits", action="store_true", help="autoriser les chiffres dans les mots")
    w.add_argument("--wl-hyphen", action="store_true", help="garder les mots composés (peut-être, grand-mère)")
    w.add_argument("--wl-sort", default="freq", choices=["freq", "alpha", "none"], help="ordre : fréquence (défaut), alphabétique, ou ordre d'apparition")
    w.add_argument("--wl-min-count", type=int, default=1, help="ne garder que les entrées vues au moins N fois")
    w.add_argument("--wl-limit", type=int, default=500_000, help="max entrées écrites (défaut 500000)")
    w.add_argument("--wl-dir", help="dossier de sortie (défaut ~/wordlists/scrapaud/<sujet>_<date>/)")
    w.add_argument("--wl-split", action="store_true", help="écrire aussi un .txt par source")
    w.add_argument("--no-live", action="store_true", help="désactiver le tableau de bord temps réel")
    o = ap.add_argument_group("sortie")
    o.add_argument("-o", "--output", help="fichier .json .csv .md .html .txt")
    o.add_argument("-i", "--interactive", action="store_true", help="interface de sélection : coche les résultats de recherche, les entrées d'une liste (--textlist) ou les liens scrapés")
    o.add_argument("--plain", action="store_true", help="avec -i : liste numérotée en texte au lieu de l'interface curses")
    o.add_argument("--json", action="store_true", help="afficher le résultat complet en JSON sur stdout (pour jq)")
    o.add_argument("--csv-raw", action="store_true", help="CSV sans neutralisation des formules (=, +, -, @ en début de cellule)")
    o.add_argument("--urls-only", action="store_true", help="n'affiche que les URLs (pipe)")
    o.add_argument("--quiet", action="store_true", help="pas de bannière ni de progression")
    o.add_argument("--no-color", action="store_true")
    cfg = load_config(sys.argv[1:] if argv is None else argv)
    valid = {act.dest for act in ap._actions}
    for k in list(cfg):
        if k.replace("-", "_") not in valid:
            print(f"[!] config : clé inconnue « {k} » ignorée", file=sys.stderr)
            del cfg[k]
    ap.set_defaults(**{k.replace("-", "_"): v for k, v in cfg.items()})
    a = ap.parse_args(argv)

    a._extract = set(EXTRACTS) if a.extract == "all" else {e.strip() for e in a.extract.split(",") if e.strip()}
    bad = a._extract - set(EXTRACTS)
    if bad:
        ap.error(f"extraction inconnue : {', '.join(sorted(bad))}")
    a._engines = [e.strip().lower() for e in a.engine.split(",") if e.strip()]
    if a._engines not in (["auto"], ["all"]):
        unk = [e for e in a._engines if e not in ENGINES]
        if unk:
            ap.error(f"moteur inconnu : {', '.join(unk)} (dispo : {', '.join(ENGINES)})")
    if not a.searx and not a.no_searx:
        try:  # instance locale auto-hébergée détectée automatiquement
            urllib.request.urlopen("http://127.0.0.1:8888/healthz", timeout=0.5).close()
            a.searx = "http://127.0.0.1:8888"
        except Exception:
            pass
    if "searxng" in a._engines and not a.searx:
        ap.error("le moteur searxng demande --searx URL (ou SCRAPAUD_SEARX)")
    try:
        a._grep = re.compile(a.grep, re.I) if a.grep else None
        a._exclude = re.compile(a.exclude, re.I) if a.exclude else None
    except re.error as e:
        ap.error(f"regex invalide : {e}")
    if a.paste_sites == "all":
        a._paste_sites = list(PASTE_DOMAINS)
    else:
        a._paste_sites = [d.strip() for d in a.paste_sites.split(",") if d.strip()]
        unk = [d for d in a._paste_sites if d not in PASTE_DOMAINS]
        if unk:
            ap.error(f"site de paste inconnu : {', '.join(unk)} (dispo : {', '.join(PASTE_DOMAINS)})")
    a._paste_q = None  # rempli dans main() pour --pastebin (les -q servent alors de filtre)
    a.main = a.wordlist if a.main is None else a.main
    a.cookie = read_secret_arg(a.cookie or os.environ.get("SCRAPAUD_COOKIE"), "--cookie")
    hdrs = []
    for h in a.header:
        h = read_secret_arg(h, "-H")
        hdrs += [x.strip() for x in h.splitlines() if x.strip()] if h else []
    a.header = hdrs
    a._scope = set()
    a._explicit = set()
    a._trusted = {h.lower() for h in a.allow_host}
    a._wl_stop = set()
    a._wl_auto = False
    for lang in (x.strip().lower() for x in (a.wl_stopwords or "").split(",") if x.strip()):
        if lang == "auto":
            a._wl_auto = True
            continue
        if lang not in STOPWORDS:
            ap.error(f"mots vides inconnus : {lang} (dispo : {', '.join(STOPWORDS)})")
        a._wl_stop |= STOPWORDS[lang]
    a._categories = [c.strip().lower() for c in (a.category or "").split(",") if c.strip()]
    if a.no_color:
        global _color
        _color = False
    return a, ap


def read_secret_arg(value, what):
    """`@fichier` (comme curl) : lit la valeur dans un fichier pour qu'elle n'apparaisse ni dans `ps` ni dans l'historique du shell."""
    if not (value and value.startswith("@")):
        return value
    path = os.path.expanduser(value[1:])
    try:
        st = os.stat(path)
        with open(path, encoding="utf-8") as f:
            data = f.read().strip()
    except OSError as e:
        raise SystemExit(f"[!] {what} : fichier illisible ({path}) : {e}")
    if st.st_mode & 0o077:
        print(f"[!] {what} : {path} est lisible par d'autres utilisateurs (chmod 600 recommandé)", file=sys.stderr)
    return data


def load_config(argv):
    """Valeurs par défaut depuis un fichier TOML (clés = noms d'options sans --, ex. searx = "http://127.0.0.1:8888")."""
    path = os.environ.get("SCRAPAUD_CONFIG") or os.path.expanduser("~/.config/scrapaud/config.toml")
    for i, a in enumerate(argv):
        if a == "--config" and i + 1 < len(argv):
            path = argv[i + 1]
        elif a.startswith("--config="):
            path = a.split("=", 1)[1]
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"[!] config illisible ({path}) : {e}", file=sys.stderr)
        return {}


def read_lines(path):
    """Une entrée par ligne ; `-` = stdin (ex. scrapaud --sitemap ... --urls-only | scrapaud -f -)."""
    if path == "-":
        return [l.strip() for l in sys.stdin if l.strip() and not l.startswith("#")]
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def main():
    global ARGS, _opener
    ARGS, ap = parse_args()
    if ARGS.clear_cache:
        print(f"cache vidé : {cache_clear()} entrées ({CACHE_DIR})")
        return 0
    _opener = build_opener(ARGS.proxy)
    if ARGS.completion:
        print(completion_script(ap))
        return 0
    if ARGS.doctor:
        return run_doctor()
    print_banner()

    queries = list(ARGS.query)
    urls = list(ARGS.url)
    try:
        if ARGS.queries_file:
            queries += read_lines(ARGS.queries_file)
        if ARGS.file:
            urls += read_lines(ARGS.file)
    except OSError as e:
        ap.error(str(e))
    setup_security(urls)
    paste_mode = ARGS.pastes or ARGS.pastebin or ARGS.gists
    if not queries and not urls and not (ARGS.pastebin or ARGS.gists):
        ap.print_help()
        return 1
    if ARGS.pastes and not queries:
        ap.error("--pastes demande au moins un sujet (-q)")
    if (ARGS.pastebin or ARGS.gists) and queries and not ARGS.pastes:
        # scan d'archive : les -q servent de filtre sur titre/contenu
        ARGS._paste_q = re.compile("|".join(re.escape(q) for q in queries), re.I)

    data = {"searches": [], "pages": []}
    for q in ([] if paste_mode else queries):
        info(green(f"[*] recherche : {q}"))
        res = search(q)
        if not res:
            info(f"[!] aucun résultat pour « {q} » (moteurs bloqués ? essaie -e wikipedia,hn,github ou --proxy)")
        if res and ARGS.interactive:
            res = pick_results(res, q)
        data["searches"] += res
        if ARGS.follow or ARGS.textlist or ARGS.wordlist:
            urls += [r["url"] for r in res]

    if ARGS.wordlist:
        if not urls:
            info("[!] aucune source pour la wordlist")
            return 1
        return run_wordlist(urls, queries[0] if queries else urls[0])

    if ARGS.textlist:
        tl = build_textlist(urls)
        if ARGS.interactive and tl["items"]:
            tl = pick_entries(tl)
        if ARGS.output:
            save_textlist(ARGS.output, tl)
        elif ARGS.json:
            print(json.dumps(tl, ensure_ascii=False, indent=2))
        else:
            print("\n".join(i["line"] for i in tl["items"]))
        return 0

    if urls:
        data["pages"] = crawl(urls)
        if ARGS.interactive and data["pages"] and not paste_mode:
            data["pages"] = pick_links(data["pages"])

    display(data)

    if paste_mode:
        seen = set()
        try:
            while True:
                new = collect_pastes(queries, seen)
                data["pages"] += new
                display({"searches": [], "pages": new})
                if ARGS.output:
                    save(ARGS.output, data)
                if not ARGS.watch:
                    break
                info(dgreen(f"[*] prochaine passe dans {ARGS.watch}s (Ctrl-C pour arrêter)"))
                time.sleep(ARGS.watch)
        except KeyboardInterrupt:
            info("[*] arrêt")
    if ARGS.output and not paste_mode:
        save(ARGS.output, data)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
