#!/usr/bin/env python3
"""Extract one paper's Zotero annotations. Read-only; strips 🔤…🔤 machine translation.

Output is raw material sorted by reading order (sortIndex), with page as an inline
`(p.N)` tag on each entry — NOT as a section header. The final note is reorganized
by the agent along conceptual/argument logic, not by page.
"""
import sqlite3, json, os, re, argparse

DB_PATH = os.path.expanduser("~/Zotero/zotero.sqlite")
TYPE = {1: "highlight", 2: "note", 3: "image", 4: "ink", 5: "underline"}
TRANS = re.compile(r"🔤.*?🔤", re.S)  # Translate plugin machine translation


def open_db():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True)


def find_items(con, q):
    return con.execute(
        """SELECT i.itemID, v.value FROM items i
           JOIN itemData d ON d.itemID=i.itemID
           JOIN itemDataValues v ON v.valueID=d.valueID
           JOIN fields f ON f.fieldID=d.fieldID
           WHERE f.fieldName='title' AND v.value LIKE ?
           ORDER BY i.itemID""",
        (f"%{q}%",),
    ).fetchall()


def pdf_attachment(con, item_id):
    row = con.execute(
        """SELECT itemID FROM itemAttachments
           WHERE parentItemID=? AND contentType='application/pdf'
           ORDER BY itemID LIMIT 1""",
        (item_id,),
    ).fetchone()
    return row[0] if row else None


def clean(text):
    return TRANS.sub("", text or "").strip()


def page(page_label, position):
    if page_label:
        return page_label
    try:
        return str(json.loads(position).get("pageIndex", -1) + 1)
    except Exception:
        return "?"


def annotations(con, att_id):
    rows = con.execute(
        """SELECT type, text, comment, color, pageLabel, position, sortIndex
           FROM itemAnnotations WHERE parentItemID=?""",
        (att_id,),
    ).fetchall()
    out = []
    for t, text, comment, color, plabel, pos, sidx in rows:
        out.append({
            "type": TYPE.get(t, f"type{t}"),
            "page": page(plabel, pos),
            "text": clean(text),
            "comment": (comment or "").strip(),
            "color": color,
            "sort": sidx or "",
        })
    out.sort(key=lambda a: a["sort"])
    return out


def to_markdown(anns):
    """Flat list in reading order; page is an inline tag, never a header."""
    lines = []
    for i, a in enumerate(anns, 1):
        lines.append(f"[{i}] {a['type']} (p.{a['page']})")
        if a["text"]:
            lines.append(f"  HL: {a['text']}")
        if a["comment"]:
            lines.append(f"  ME: {a['comment']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="title fragment")
    ap.add_argument("--item", type=int, help="itemID (skip title search)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    con = open_db()
    if args.item:
        item_id = args.item
    else:
        hits = find_items(con, args.query)
        if not hits:
            print("no match"); return
        if len(hits) > 1:
            print("multiple matches, pass --item <id>:")
            for iid, title in hits:
                print(f"  {iid}\t{title}")
            return
        item_id = hits[0][0]

    att = pdf_attachment(con, item_id)
    if not att:
        print(f"no PDF attachment for item {item_id}"); return
    anns = annotations(con, att)

    if args.json:
        print(json.dumps({"item": item_id, "count": len(anns), "annotations": anns},
                         ensure_ascii=False, indent=2))
    else:
        n_note = sum(a["type"] == "note" for a in anns)
        n_cmt = sum(bool(a["comment"]) for a in anns)
        print(f"item={item_id} total={len(anns)} highlight={len(anns)-n_note} "
              f"note={n_note} with_comment={n_cmt}")
        print(to_markdown(anns))


if __name__ == "__main__":
    main()
