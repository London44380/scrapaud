import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import unquote
import jsbeautifier

# ========== PARAMÈTRES DE SÉCURITÉ ==========
URL = "https://exemple.com"  # <-- Mets ici l'URL à tester
MAX_HTML_SIZE = 2_000_000    # 2 Mo max pour la page HTML
MAX_TEXT_SIZE = 2_000_000    # 2 Mo max pour les fragments de texte

headers = {"User-Agent": "Mozilla/5.0"}

# ========== TÉLÉCHARGEMENT SÉCURISÉ ==========
try:
    response = requests.get(URL, headers=headers, timeout=10)
    response.raise_for_status()
    response.encoding = response.apparent_encoding  # Détection auto encodage
except Exception as e:
    print("Erreur lors du téléchargement :", e)
    exit()

if len(response.text) > MAX_HTML_SIZE:
    print(f"Page trop volumineuse ({len(response.text)//1024} Ko), arrêt du script.")
    exit()

html = response.text

# ========== PARSING SÉCURISÉ ==========
try:
    soup = BeautifulSoup(html, "html.parser")
except Exception as e:
    print("Erreur lors du parsing HTML :", e)
    exit()

# ========== EXTRACTION DES FRAGMENTS ==========
all_texts = []

# Texte visible
visible_text = soup.get_text(separator='\n', strip=True)
if len(visible_text) > MAX_TEXT_SIZE:
    print("Texte visible trop volumineux, tronqué pour analyse.")
    visible_text = visible_text[:MAX_TEXT_SIZE]
all_texts.append(visible_text)

# Attributs HTML (inclut mailto:/tel:)
for tag in soup.find_all(True):
    for attr in tag.attrs:
        value = tag.attrs[attr]
        if isinstance(value, list):
            value = " ".join(value)
        if value and isinstance(value, str) and len(value) < MAX_TEXT_SIZE:
            if attr in ["href", "src"]:
                if value.startswith("mailto:"):
                    all_texts.append(value[7:])
                elif value.startswith("tel:"):
                    all_texts.append(value[4:])
            all_texts.append(value)

# Scripts et meta
for script in soup.find_all(['script', 'meta']):
    content = script.string or script.get('content', '')
    if content and len(content) < MAX_TEXT_SIZE:
        all_texts.append(content)

# Valeurs URL décodées
for line in all_texts[:]:
    decoded = unquote(line)
    if decoded != line and len(decoded) < MAX_TEXT_SIZE:
        all_texts.append(decoded)

# Fragments collés (HTML sans balises)
joined_html = re.sub(r'<[^>]+>', '', html)
if len(joined_html) > MAX_TEXT_SIZE:
    print("Fragment HTML sans balises trop volumineux, tronqué pour analyse.")
    joined_html = joined_html[:MAX_TEXT_SIZE]
all_texts.append(joined_html)

# ========== RECHERCHE DES EMAILS & TÉLÉPHONES ==========
emails = set()
phones = set()

# Email classique
email_regex = r'[\w\.-]+@[\w\.-]+\.\w+'

# Email obfusqué type [at], [dot], (at), {dot}, etc
obfuscation_regexes = [
    r'([a-zA-Z0-9_.+-]+)\s*(?:\[|\(|\{)?\s*(at|@)\s*(?:\]|\)|\})?\s*([a-zA-Z0-9_.+-]+)\s*(?:\[|\(|\{)?\s*(dot|\.)\s*(?:\]|\)|\})?\s*([a-zA-Z0-9_.+-]+)'
    # Ajoute d'autres motifs si nécessaire
]

# Téléphone français et formats courants
phone_regex = r'''
    (?:(?:\+33|0033|0)[\s\.-]*[1-9](?:[\s\.-]*\d{2}){4})      # +33 6 12 34 56 78 ou 06 12 34 56 78
    |(?:\d{2}[\s\.-]){4}\d{2}                                 # 06-12-34-56-78
    |(?:\(?\d{2,4}\)?[\s\.-]*){2,5}                           # Formats internationaux
'''

for text in all_texts:
    # Recherche emails classiques
    for email in re.findall(email_regex, text, re.I):
        emails.add(email)
    # Recherche emails obfusqués (tous patterns)
    for regex in obfuscation_regexes:
        for match in re.findall(regex, text, re.I):
            if len(match) == 5:
                emails.add(f"{match[0]}@{match[2]}.{match[4]}")
    # Recherche téléphones
    for phone in re.findall(phone_regex, text, re.VERBOSE):
        clean = re.sub(r'[\s\.-]', '', phone)
        if len(clean) > 8:  # filtre basique
            phones.add(clean)

# ========== HEURISTIQUES JS : Emails cachés dans le JavaScript ==========
js_emails = set()
script_blocks = [script.string or script.get('content', '') for script in soup.find_all('script')]
for js in script_blocks:
    if not js or len(js) > MAX_TEXT_SIZE:
        continue
    beautified = jsbeautifier.beautify(js)

    # Heuristique 1: ['contact','exemple','com'].join('.')
    join_match = re.findall(r"\[(['\"].+?['\"].+?)\]\.join\(['\"]([.@-])['\"]\)", beautified, re.DOTALL)
    for array_str, sep in join_match:
        parts = re.findall(r"'([^']+)'|\"([^\"]+)\"", array_str)
        email = sep.join([x[0] or x[1] for x in parts])
        if '@' in email and '.' in email:
            js_emails.add(email)

    # Heuristique 2: reverse + join
    rev_match = re.findall(r"\[(['\"].+?['\"].+?)\]\.reverse\(\)\.join\(['\"]([.@-])['\"]\)", beautified, re.DOTALL)
    for array_str, sep in rev_match:
        parts = re.findall(r"'([^']+)'|\"([^\"]+)\"", array_str)
        email = sep.join(reversed([x[0] or x[1] for x in parts]))
        if '@' in email and '.' in email:
            js_emails.add(email)

    # Heuristique 3: concaténation de chaînes
    concat_match = re.findall(r"(?:var|let|const)\s+\w+\s*=\s*((?:['\"][^'\"]+['\"]\s*\+\s*)+['\"][^'\"]+['\"])", beautified)
    for concat_str in concat_match:
        parts = re.findall(r"'([^']+)'|\"([^\"]+)\"", concat_str)
        email = ''.join([x[0] or x[1] for x in parts])
        if '@' in email and '.' in email:
            js_emails.add(email)

    # Heuristique 4: reverse d'une string
    split_join_match = re.findall(
        r"['\"]([^'\"]+)['\"]\.split\(['\"]{0,1}['\"]{0,1}\)\.reverse\(\)\.join\(['\"]{0,1}['\"]{0,1}\)", beautified)
    for rev_email in split_join_match:
        email = rev_email[::-1]
        if '@' in email and '.' in email:
            js_emails.add(email)

# Ajoute les emails JS aux emails globaux
emails = emails.union(js_emails)

# ========== NETTOYAGE DES EMAILS ==========
def clean_email(email):
    email = email.replace(' ', '')
    email = re.sub(r'\.+', '.', email)
    email = email.replace('.@', '@')
    return email

emails = {clean_email(email) for email in emails}

# ========== AFFICHAGE ==========
print("=== Emails détectés ===")
if not emails:
    print("Aucun email trouvé.")
else:
    for email in sorted(emails):
        print(" -", email)

print("\n=== Téléphones détectés ===")
if not phones:
    print("Aucun numéro trouvé.")
else:
    for phone in sorted(phones):
        print(" -", phone)