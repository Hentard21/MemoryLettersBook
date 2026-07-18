# -*- coding: utf-8 -*-
"""Разбивает содержание на 4 сбалансированных блока (2 разворота × 2 страницы)
и вставляет в book.html вместо плейсхолдеров CONTENTS_1A/1B/2A/2B."""
import json, os, re
from collections import OrderedDict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
contents = json.load(open(f"{BASE}/content/front-matter/contents.json", encoding="utf-8"))
fams = contents["families"]

groups = OrderedDict()
for f in fams:
    groups.setdefault(f["region"], []).append(f)
groups = list(groups.items())

def lines(entries): return 1.8 + len(entries)
total = sum(lines(e) for _, e in groups)
target = total / 4

buckets, cur, acc = [], [], 0
for region, entries in groups:
    cur.append((region, entries)); acc += lines(entries)
    if acc >= target and len(buckets) < 3:
        buckets.append(cur); cur, acc = [], 0
buckets.append(cur)
while len(buckets) < 4: buckets.append([])

def child_phrase(f):
    a = f["authors"]
    if not a: return "письмо ребёнка"
    return ("письмо · " + a[0]) if len(a) == 1 else ("письма · " + ", ".join(a))

def render(bucket):
    h = ['<div class="toc-cols">']
    for region, entries in bucket:
        h.append('<div class="toc-group"><h3 class="toc-region">%s</h3>' % region)
        for f in entries:
            h.append('<p class="toc-row"><span class="toc-hero">%s</span>'
                     '<span class="toc-auth">%s</span><span class="toc-dots"></span>'
                     '<span class="toc-pg">%d</span></p>' % (f["hero_name"], child_phrase(f), f["page"]))
        h.append('</div>')
    h.append('</div>')
    return "\n".join(h)

book = open(f"{BASE}/design/prototypes/print-v3/book.html", encoding="utf-8").read()
for slot, bucket in zip(["1A","1B","2A","2B"], buckets):
    book = book.replace(f"<!--CONTENTS_{slot}-->", render(bucket))
open(f"{BASE}/design/prototypes/print-v3/book.html", "w", encoding="utf-8").write(book)
print("Содержание вставлено. Регионов в блоках:", [len(b) for b in buckets],
      "| семей:", [sum(len(e) for _, e in b) for b in buckets])
