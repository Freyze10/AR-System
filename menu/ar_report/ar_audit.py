"""Builds the audit trail text for AR saves and updates."""
from workstation.workstation import get_real_mac

_FIELDS = ("Quantity", "Unit", "Product Code", "Product Color", "Lot No.", "Note")
_MIN_SIMILARITY = 2   # an old and a new item need at least this many equal, non-empty fields to count as "the same item, edited"


def workstation_mac():
    """The MAC of this PC, read the same way login registers it (db/workstation.py)."""
    return get_real_mac()


def normalize_item(qty, unit, code, color, lot, note):
    """One item as a comparable tuple: (qty, unit, code, color, lot, note)."""
    return (round(float(qty or 0), 6), (unit or "").strip(), (code or "").strip(),
            (color or "").strip(), (lot or "").strip(), (note or "").strip())


def _show(index, value):
    if index == 0:
        return f"{value:,.3f}"
    return value if value else "(blank)"


def _date(d):
    return d.strftime("%m/%d/%Y") if d else "(blank)"


def _describe(item):
    qty, unit, code, color, lot, note = item
    return f"{qty:,.3f} {unit} | {code} | {color} | Lot: {lot or '-'} | Note: {note or '-'}"


def _similarity(a, b):
    return sum(1 for x, y in zip(a, b) if x == y and x not in ("", None))


def _compare_items(old, new):
    """Returns (changed, removed, added).
    changed = [(old_index, new_index)], removed = [old_index], added = [new_index].

    Editing an item in the form means Remove then Add, so the edited item ends up
    at the bottom of the table. Items are therefore matched by content, not by
    position: identical items first, then the most similar leftovers."""
    old_left = list(range(len(old)))
    new_left = list(range(len(new)))

    for i in list(old_left):                       # 1. untouched items
        for j in new_left:
            if old[i] == new[j]:
                old_left.remove(i)
                new_left.remove(j)
                break

    candidates = sorted(                            # 2. edited items
        ((_similarity(old[i], new[j]), i, j) for i in old_left for j in new_left),
        key=lambda t: (-t[0], t[1], t[2]))
    changed = []
    for score, i, j in candidates:
        if score < _MIN_SIMILARITY:
            break
        if i in old_left and j in new_left:
            changed.append((i, j))
            old_left.remove(i)
            new_left.remove(j)

    return sorted(changed), old_left, new_left      # 3. what is left was removed / added


def describe_save(ar_no, customer, item_count):
    return f"AR NO: {ar_no:07d} for customer {customer} with {item_count} item(s)"


def describe_update(ar_no, old, new):
    """old / new = {"customer": str, "ar_date": date, "items": [normalized item tuples]}"""
    lines = []

    if old["customer"] != new["customer"]:
        lines.append(f'Customer: "{old["customer"]}" -> "{new["customer"]}"')
    if old["ar_date"] != new["ar_date"]:
        lines.append(f"AR Date: {_date(old['ar_date'])} -> {_date(new['ar_date'])}")
    if len(old["items"]) != len(new["items"]):
        lines.append(f"No. of Items: {len(old['items'])} -> {len(new['items'])}")

    changed, removed, added = _compare_items(old["items"], new["items"])
    for i, j in changed:
        a, b = old["items"][i], new["items"][j]
        lines.append(f"Item {i + 1} changed ({a[2]} / {a[3]}):")
        for k, name in enumerate(_FIELDS):
            if a[k] != b[k]:
                lines.append(f"    {name}: {_show(k, a[k])} -> {_show(k, b[k])}")
    for i in removed:
        lines.append(f"Item {i + 1} removed: {_describe(old['items'][i])}")
    for j in added:
        lines.append(f"Item {j + 1} added: {_describe(new['items'][j])}")

    head = f"AR NO: {ar_no:07d} for customer {new['customer']} updated"
    return head + (" (no changes)" if not lines else "\n" + "\n".join(lines))