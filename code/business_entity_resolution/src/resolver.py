import os
import re
import difflib
import unicodedata
from collections import defaultdict
from typing import Dict, List, Set, Tuple
import pandas as pd

DEV_MAP = {
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo', 'ऋ': 'ri',
    'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'अं': 'am', 'अः': 'ah',
    'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
    'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
    'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h',
    'ा': 'a', 'ि': 'i', 'ी': 'i', 'ु': 'u', 'ू': 'u', 'ृ': 'ri',
    'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ं': 'n', 'ँ': 'n', 'ः': 'h', '्': '',
    '़': '', 'ॉ': 'o', 'ॅ': 'e', '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
    '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'
}

def to_ascii(text: str) -> str:
    if not text:
        return ''
    chars = [DEV_MAP.get(c, c) for c in str(text)]
    return unicodedata.normalize('NFKD', ''.join(chars)).encode('ascii', 'ignore').decode('ascii').lower()

AKA_REGEX = re.compile(r'^(?:m/s\s+|c/o\s+)?(.*?)(?:\s+(?:aka|d/b/a|trading\s+as|t/a)\s+(.*))?$', re.IGNORECASE)
DOMAIN_REGEX = re.compile(r'^(?:https?://)?(?:www\.)?([a-z0-9\-]+)\.(?:com|org|net|in|fr|co|io|biz|info)(?:/.*)?$', re.IGNORECASE)
PREFIX_REGEX = re.compile(r'^(?:m/s\.?|c/o\.?|dr\.?|shri\.?|sri\.?|smt\.?|mr\.?|mrs\.?)\s+', re.IGNORECASE)

LEGAL_SUFFIXES_REGEX = re.compile(
    r'\b('
    r'private\s+limited|pvt\.?\s*ltd\.?|p\.?\s*ltd\.?|'
    r'private|pvt\.?|limited|ltd\.?|'
    r'incorporated|inc\.?|corporation|corp\.?|company|co\.?|'
    r'llc|l\.l\.c\.|pllc|llp|l\.l\.p\.|l\.p\.|lp|'
    r'sarl|s\.a\.r\.l\.|sasu|s\.a\.s\.u\.|sas|s\.a\.s\.|'
    r'eurl|e\.u\.r\.l\.|sa|s\.a\.|sci|s\.c\.i\.|snc|s\.n\.c\.|'
    r'et\s+fils|&\s+fils'
    r')\b',
    re.IGNORECASE,
)

NAME_STOPWORDS = {
    'and', '&', 'the', 'of', 'in', 'at', 'for', 'on', 'by', 'with',
    'de', 'du', 'des', 'le', 'la', 'les', 'et', 'en', 'd', 'l',
    'services', 'service', 'solutions', 'enterprises', 'enterprise',
    'group', 'holdings', 'holding', 'associates', 'consultants', 'consulting',
    'management', 'industries', 'international', 'global', 'national',
    'trading', 'agency', 'center', 'centre', 'club', 'praivet'
}

ADDRESS_ABBREVIATIONS = {
    'st': 'street', 'str': 'street', 'rd': 'road', 'ave': 'avenue', 'av': 'avenue',
    'blvd': 'boulevard', 'bd': 'boulevard', 'dr': 'drive', 'ln': 'lane', 'ct': 'court',
    'pl': 'place', 'hwy': 'highway', 'pkwy': 'parkway', 'apt': 'apartment', 'ste': 'suite',
    'bldg': 'building', 'fl': 'floor', 'sq': 'square', 'ter': 'terrace', 'r': 'rue',
    'imp': 'impasse', 'all': 'allee', 'che': 'chemin', 'rt': 'route'
}

def clean_name_variants(raw_name: str) -> List[str]:
    if not raw_name:
        return ['']
    ascii_nm = to_ascii(raw_name)
    m = AKA_REGEX.match(ascii_nm)
    variants = []
    if m:
        p1 = m.group(1).strip()
        p2 = m.group(2).strip() if m.group(2) else ''
        if p1: variants.append(p1)
        if p2: variants.append(p2)
    else:
        variants.append(ascii_nm)
        
    cleaned = []
    for var in variants:
        dm = DOMAIN_REGEX.match(var)
        if dm:
            var = dm.group(1).replace('-', ' ')
        var = PREFIX_REGEX.sub('', var)
        var = re.sub(r'\b\d{7,}\b', ' ', var)
        for _ in range(2):
            var = LEGAL_SUFFIXES_REGEX.sub(' ', var)
        var = re.sub(r'[^\w\s]', ' ', var)
        var = re.sub(r'\s+', ' ', var).strip()
        if var:
            cleaned.append(var)
    return cleaned if cleaned else [ascii_nm]

def get_compact(name_cleaned: str) -> str:
    return re.sub(r'[^\w]', '', name_cleaned)

def clean_address(address: str) -> str:
    if not address:
        return ''
    text = to_ascii(address)
    text = re.sub(r'\b(null|nan|none|unknown)\b', ' ', text)
    text = re.sub(r'\b0+(\d+)\b', r'\1', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = text.split()
    return ' '.join([ADDRESS_ABBREVIATIONS.get(t, t) for t in tokens])

def extract_all_nums(addr: str) -> Set[str]:
    if not addr: return set()
    nums = re.findall(r'\d+', to_ascii(addr))
    return {n.lstrip('0') or '0' for n in nums}

class CountryResolver:
    """
    Production entity resolution engine.
    """
    def __init__(self, s2_df: pd.DataFrame, s3_df: pd.DataFrame, country: str):
        self.country = country
        self.compact_map = defaultdict(list)
        self.token_map = defaultdict(list)
        self.addr_map = defaultdict(list)
        self.records = {}
        
        for df in [s2_df, s3_df]:
            df_c = df[df['country'] == country] if 'country' in df.columns else df
            names = df_c['business_name'].fillna('').values
            addrs = df_c['business_address'].fillna('').values
            eids = df_c['entity_id'].values
            
            for i in range(len(eids)):
                eid = eids[i]
                nm = str(names[i])
                ad = str(addrs[i])
                
                n_vars = clean_name_variants(nm)
                comps = [get_compact(v) for v in n_vars if len(get_compact(v)) >= 3]
                all_toks = set()
                for v in n_vars:
                    for t in v.split():
                        if len(t) >= 3 and t not in NAME_STOPWORDS:
                            all_toks.add(t)
                            
                cad = clean_address(ad)
                nums = extract_all_nums(ad)
                atok = set(w for w in cad.split() if not w.isdigit() and len(w) >= 3)
                
                self.records[eid] = (nm, ad, comps, all_toks, nums, atok)
                
                for comp in comps:
                    self.compact_map[comp].append(eid)
                for t in all_toks:
                    self.token_map[t].append(eid)
                if nums and atok:
                    top_words = sorted(list(atok), key=len, reverse=True)[:3]
                    for num in sorted(nums)[:2]:
                        for w in top_words:
                            self.addr_map[(num, w[:4])].append(eid)

        # Prune very frequent generic tokens to keep candidate set clean
        self.token_map = {k: v for k, v in self.token_map.items() if len(v) <= 250}
        self.addr_map = {k: v for k, v in self.addr_map.items() if len(v) <= 100}

    def resolve(self, name: str, addr: str) -> Tuple[List[str], List[str]]:
        cands = []
        cands_set = set()
        
        n_vars = clean_name_variants(name)
        comps = [get_compact(v) for v in n_vars if len(get_compact(v)) >= 3]
        all_toks = set()
        for v in n_vars:
            for t in v.split():
                if len(t) >= 3 and t not in NAME_STOPWORDS:
                    all_toks.add(t)
                    
        cad = clean_address(addr)
        nums = extract_all_nums(addr)
        atok = set(w for w in cad.split() if not w.isdigit() and len(w) >= 3)
        
        def add_cands(new_ids, limit):
            added = 0
            for cid in new_ids:
                if cid not in cands_set:
                    cands_set.add(cid)
                    cands.append(cid)
                    added += 1
                    if added >= limit:
                        break
        
        # 1. Exact compact key
        for comp in comps:
            if comp in self.compact_map:
                add_cands(self.compact_map[comp], 30)
                
        # 2. Distinctive token key
        avail = [t for t in all_toks if t in self.token_map]
        avail.sort(key=lambda t: len(self.token_map[t]))
        for t in avail[:3]:
            add_cands(self.token_map[t], 20)
            if len(cands) >= 35:
                break
                
        # 3. Address key
        if nums and atok:
            top_words = sorted(list(atok), key=len, reverse=True)[:3]
            for num in sorted(nums)[:2]:
                for w in top_words:
                    key = (num, w[:4])
                    if key in self.addr_map:
                        add_cands(self.addr_map[key], 15)
                        if len(cands) >= 40:
                            break
                            
        cand_list = cands[:40]
        
        matches = []
        for cid in cand_list:
            c_nm, c_ad, c_comps, c_toks, c_nums, c_atok = self.records[cid]
            addr_conflict = False
            if nums and c_nums and not (nums & c_nums) and len(atok) >= 2 and len(c_atok) >= 2 and not (atok & c_atok):
                addr_conflict = True
                
            # Rule 1: Exact compact name match
            if not addr_conflict and any(c1 == c2 for c1 in comps for c2 in c_comps):
                matches.append(cid)
                continue
                
            # Rule 2: Typo edit ratio
            if not addr_conflict:
                matched_sim = False
                for c1 in comps:
                    for c2 in c_comps:
                        if abs(len(c1) - len(c2)) / max(len(c1), len(c2)) <= 0.20:
                            if difflib.SequenceMatcher(None, c1, c2).ratio() >= 0.80:
                                matches.append(cid)
                                matched_sim = True
                                break
                    if matched_sim:
                        break
                if matched_sim:
                    continue
                    
            # Rule 3: High token overlap
            if not addr_conflict and all_toks and c_toks:
                inter = all_toks & c_toks
                if len(inter) >= 2 and (len(inter) / min(len(all_toks), len(c_toks))) >= 0.70:
                    matches.append(cid)
                    continue
                    
            # Rule 4: Same-address match
            if nums and c_nums and (nums & c_nums) and atok and c_atok:
                addr_inter = atok & c_atok
                if len(addr_inter) >= 2 and (len(addr_inter) / min(len(atok), len(c_atok))) >= 0.50:
                    has_name_sim = bool(all_toks & c_toks) or any(difflib.SequenceMatcher(None, c1, c2).ratio() >= 0.45 for c1 in comps for c2 in c_comps)
                    if has_name_sim or not comps or not c_comps:
                        matches.append(cid)
                        continue
                    
        return cand_list, sorted(matches)
