"""
Free-text tool entry analysis - focused on drills.
Parses free-text sequence detail entries, normalizes drill sizes,
and recommends which should join the common tool kit.
"""
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('tool_frequency_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# --- Identify free-text entries (not matching standard ProShop tool number patterns) ---
freetext = []
standard = []
for t in data['tool_ranking']:
    tn = t['tool_number']
    is_std = bool(re.match(r'^[A-Z]{1,2}\d+', tn)) or bool(re.match(r'^TIPD\d+', tn))
    if is_std:
        standard.append(t)
    else:
        freetext.append(t)

freetext.sort(key=lambda x: x['wo_qty_weighted'], reverse=True)

# --- Categorize free-text entries ---
drills = []
reamers = []
taps = []
tool_refs = []  # references to standard tools with dashes (A-30, CRIB L-18)
junk = []       # non-tool entries

for t in freetext:
    tn = t['tool_number'].upper()

    # Junk / non-tool
    if tn in ['-', 'YOU', 'DRILL DRAWER', 'STORED W/ FIXTURE',
              'ON TOP OF SHELF NEXT TO LATHE', 'CRIB', '']:
        junk.append(t)
        continue

    # References to standard tools (A-30, L-18, CRIB O-4, etc.)
    if re.match(r'^[A-Z]-\d+', tn) or re.match(r'^[A-Z]-[A-Z]\d+', tn) or tn.startswith('CRIB '):
        tool_refs.append(t)
        continue

    # Drills
    drill_keywords = ['DRILL', 'JOBBER', 'STUB', '.120', '.166', '.0995',
                       '.1015', '.111', '.201', '.277', '.302', '.218',
                       '.18 DIAMETER', '13-64', '.15748', 'NO.', 'NO ',
                       'LETTER', '#55', '#30']
    if any(x in tn for x in drill_keywords):
        drills.append(t)
        continue

    # Reamers
    if 'REAMER' in tn:
        reamers.append(t)
        continue

    # Taps
    if 'TAP' in tn:
        taps.append(t)
        continue

    # Catch remaining numbered drills
    if re.match(r'^#\d+', tn) or re.match(r'^NO\.?\s*\d+', tn):
        drills.append(t)
        continue

    # Everything else goes to tool_refs
    tool_refs.append(t)

# --- Print category summary ---
print("=" * 85)
print("FREE-TEXT TOOL ENTRY ANALYSIS")
print("=" * 85)
print(f"Total free-text entries:  {len(freetext)}")
print(f"  Drills:                 {len(drills)}")
print(f"  Reamers:                {len(reamers)}")
print(f"  Taps:                   {len(taps)}")
print(f"  Refs to std tools:      {len(tool_refs)}  (A-30, CRIB L-18, etc.)")
print(f"  Junk/non-tool:          {len(junk)}")

# --- Drill size normalization ---
# Number drill → diameter map
num_drill = {
    55: 0.052, 54: 0.055, 53: 0.0595, 52: 0.0635, 51: 0.067,
    50: 0.070, 49: 0.073, 48: 0.076, 47: 0.0785, 46: 0.081,
    45: 0.082, 44: 0.086, 43: 0.089, 42: 0.0935, 41: 0.096,
    40: 0.098, 39: 0.0995, 38: 0.1015, 37: 0.104, 36: 0.1065,
    35: 0.110, 34: 0.111, 33: 0.113, 32: 0.116, 31: 0.120,
    30: 0.1285, 29: 0.136, 28: 0.1405, 27: 0.144, 26: 0.147,
    25: 0.1495, 24: 0.152, 23: 0.154, 22: 0.157, 21: 0.159,
    20: 0.161, 19: 0.166, 18: 0.1695, 17: 0.173, 16: 0.177,
    15: 0.180, 14: 0.182, 13: 0.185, 12: 0.189, 11: 0.191,
    10: 0.1935, 9: 0.196, 8: 0.199, 7: 0.201, 6: 0.204,
    5: 0.2055, 4: 0.209, 3: 0.213, 2: 0.221, 1: 0.228,
}

letter_drill = {
    'A': 0.234, 'B': 0.238, 'C': 0.242, 'D': 0.246, 'E': 0.250,
    'F': 0.257, 'G': 0.261, 'H': 0.266, 'I': 0.272, 'J': 0.277,
    'K': 0.281, 'L': 0.290, 'M': 0.295, 'N': 0.302, 'O': 0.316,
    'P': 0.323, 'Q': 0.332, 'R': 0.339, 'S': 0.348, 'T': 0.358,
    'U': 0.368, 'V': 0.377, 'W': 0.386, 'X': 0.397, 'Y': 0.404,
    'Z': 0.413,
}


def parse_drill_diameter(name):
    """Try to extract drill diameter from free-text name."""
    n = name.upper().strip()

    # Try number drill: #16, NO. 16, NO.16, No. 25, etc.
    m = re.search(r'(?:#|NO\.?\s*#?\s*)(\d+)', n)
    if m:
        num = int(m.group(1))
        if num in num_drill:
            return num_drill[num], f"#{num}"

    # Try letter drill: LETTER P, LETTER W, etc.
    m = re.search(r'LETTER\s*\(?([A-Z])\)?', n)
    if m:
        letter = m.group(1)
        if letter in letter_drill:
            return letter_drill[letter], f"Letter {letter}"

    # Try direct decimal: .166, 0.1285, .120, etc.
    m = re.search(r'(\d*\.\d+)\s*"?\s*(?:JOBBER|HSS|DRILL|COBALT|DIAMETER|DIA|UNUSUAL|THREE|DEGREE|135|LONG)?', n)
    if m:
        try:
            dia = float(m.group(1))
            if 0.01 < dia < 1.5:  # reasonable drill diameter
                return dia, f"{dia:.4f}\""
        except ValueError:
            pass

    # Try fraction: 5/8, 3/8, 11/64, 7/32, etc.
    m = re.search(r'(\d+)/(\d+)', n)
    if m:
        dia = int(m.group(1)) / int(m.group(2))
        if 0.01 < dia < 1.5:
            return dia, f"{m.group(1)}/{m.group(2)}"

    # Try 13-64 style
    m = re.search(r'(\d+)-(\d+)', n)
    if m:
        num, denom = int(m.group(1)), int(m.group(2))
        if denom in [8, 16, 32, 64] and num < denom:
            return num / denom, f"{num}/{denom}"

    return None, None


# --- Aggregate drill sizes ---
drill_sizes = {}
unparsed = []

for t in drills:
    dia, common_name = parse_drill_diameter(t['tool_number'])
    if dia:
        dia_key = f"{dia:.4f}"
        if dia_key not in drill_sizes:
            drill_sizes[dia_key] = {
                'diameter': dia,
                'common_name': common_name,
                'wo_qty': 0,
                'wo_count': 0,
                'parts': set(),
                'refs': [],
            }
        drill_sizes[dia_key]['wo_qty'] += t['wo_qty_weighted']
        drill_sizes[dia_key]['wo_count'] += t['wo_count']
        drill_sizes[dia_key]['refs'].append(t['tool_number'])
        for p in t['parts']:
            drill_sizes[dia_key]['parts'].add(p)
    else:
        unparsed.append(t)

# Also add reamers (they represent hole sizes too)
for t in reamers:
    dia, common_name = parse_drill_diameter(t['tool_number'])
    if dia:
        dia_key = f"{dia:.4f}"
        if dia_key not in drill_sizes:
            drill_sizes[dia_key] = {
                'diameter': dia,
                'common_name': common_name + " (reamer)",
                'wo_qty': 0,
                'wo_count': 0,
                'parts': set(),
                'refs': [],
            }
        drill_sizes[dia_key]['wo_qty'] += t['wo_qty_weighted']
        drill_sizes[dia_key]['wo_count'] += t['wo_count']
        drill_sizes[dia_key]['refs'].append(t['tool_number'])
        for p in t['parts']:
            drill_sizes[dia_key]['parts'].add(p)

# --- Also pull standard TIPD and D-group drills for comparison ---
std_drills = []
for t in standard:
    tn = t['tool_number']
    desc = t.get('description', '').upper()
    if tn.startswith('TIPD') or (tn.startswith('D') and ('DRILL' in desc or 'DR ' in desc)):
        std_drills.append(t)
    elif tn.startswith('E') and 'CENTER DRILL' in desc:
        std_drills.append(t)
    elif tn.startswith('O') and ('SPOT' in desc or 'SPOTTING' in desc or 'COUNTERSINK' in desc):
        std_drills.append(t)

# --- Print results ---

print("\n" + "=" * 85)
print("FREE-TEXT DRILLS - NORMALIZED BY DIAMETER")
print("=" * 85)

sorted_sizes = sorted(drill_sizes.values(), key=lambda x: x['wo_qty'], reverse=True)

print(f"\n{'Dia (in)':<11} {'Common':<18} {'WO Qty':<8} {'Parts':<6} Free-text References")
print(f"{'-'*11} {'-'*18} {'-'*8} {'-'*6} {'-'*45}")

for info in sorted_sizes:
    refs = ", ".join(info['refs'][:3])
    if len(info['refs']) > 3:
        refs += f" +{len(info['refs'])-3}"
    n_parts = len(info['parts'])
    print(f"{info['diameter']:<11.4f} {info['common_name']:<18} {info['wo_qty']:<8} {n_parts:<6} {refs}")

# --- Standard drills for comparison ---
print("\n" + "=" * 85)
print("STANDARD (PROSHOP-REGISTERED) DRILLS FOR COMPARISON")
print("=" * 85)

std_drills.sort(key=lambda x: x['wo_qty_weighted'], reverse=True)

print(f"\n{'Tool #':<12} {'WO Qty':<8} {'Parts':<6} {'WOs':<5} Description")
print(f"{'-'*12} {'-'*8} {'-'*6} {'-'*5} {'-'*50}")

for t in std_drills[:25]:
    desc = t['description'][:50] if t['description'] else '(no desc)'
    print(f"{t['tool_number']:<12} {t['wo_qty_weighted']:<8} {t['part_count']:<6} {t['wo_count']:<5} {desc}")

# --- Combined drill kit recommendation ---
print("\n" + "=" * 85)
print("COMBINED DRILL KIT RECOMMENDATION")
print("(Free-text drills + standard drills, ranked by WO volume)")
print("=" * 85)

combined = []

# Add free-text drills
for info in sorted_sizes:
    combined.append({
        'name': f"{info['common_name']} ({info['diameter']:.4f}\")",
        'wo_qty': info['wo_qty'],
        'parts': len(info['parts']),
        'source': 'free-text',
        'refs': info['refs'],
        'diameter': info['diameter'],
    })

# Add standard drills
for t in std_drills:
    combined.append({
        'name': f"{t['tool_number']}: {t['description'][:35]}",
        'wo_qty': t['wo_qty_weighted'],
        'parts': t['part_count'],
        'source': 'standard',
        'refs': [],
        'diameter': 0,
    })

combined.sort(key=lambda x: x['wo_qty'], reverse=True)

print(f"\n{'Rank':<5} {'WO Qty':<8} {'Parts':<6} {'Source':<10} Drill")
print(f"{'-'*5} {'-'*8} {'-'*6} {'-'*10} {'-'*50}")

for i, d in enumerate(combined[:40], 1):
    marker = " <-- KIT" if d['wo_qty'] >= 200 and d['parts'] >= 2 else ""
    print(f"{i:<5} {d['wo_qty']:<8} {d['parts']:<6} {d['source']:<10} {d['name']}{marker}")

# --- Taps summary ---
if taps:
    print("\n" + "=" * 85)
    print("FREE-TEXT TAPS")
    print("=" * 85)
    print(f"\n{'WO Qty':<8} {'Parts':<6} Tap Reference")
    print(f"{'-'*8} {'-'*6} {'-'*45}")
    for t in taps:
        print(f"{t['wo_qty_weighted']:<8} {t['part_count']:<6} {t['tool_number']}")

# --- Tool reference aliases (data quality issue) ---
print("\n" + "=" * 85)
print("ALIAS REFERENCES (same tools entered with dashes/CRIB prefix)")
print("These should be normalized to their standard ProShop tool numbers.")
print("=" * 85)

tool_refs.sort(key=lambda x: x['wo_qty_weighted'], reverse=True)
print(f"\n{'WO Qty':<8} {'Parts':<6} {'Seq':<5} Free-text        --> Should be")
print(f"{'-'*8} {'-'*6} {'-'*5} {'-'*18} {'-'*15}")

for t in tool_refs[:25]:
    tn = t['tool_number']
    # Guess the canonical form
    canonical = tn.upper().replace('CRIB ', '').replace('-', '').strip()
    # Try to match: A-30 -> A30, CRIB O-4 -> O4, etc.
    m = re.match(r'^([A-Z])(\d+)', canonical)
    if m:
        canonical = m.group(1) + m.group(2)
    print(f"{t['wo_qty_weighted']:<8} {t['part_count']:<6} {t['sequence_appearances']:<5} {tn:<18} --> {canonical}")

# --- Unparsed ---
if unparsed:
    print("\n" + "=" * 85)
    print(f"UNPARSED DRILL REFERENCES ({len(unparsed)} entries)")
    print("=" * 85)
    for t in unparsed:
        print(f"  {t['wo_qty_weighted']:<8} {t['tool_number']}")

# Final summary
print("\n" + "=" * 85)
print("SUMMARY & RECOMMENDATIONS")
print("=" * 85)
print("""
1. DATA QUALITY: Many sequence details use free-text drill descriptions instead
   of ProShop tool numbers. This creates duplicates and makes analysis harder.
   Consider standardizing these to use TIPD/D-series tool numbers.

2. ALIAS CLEANUP: Tool references like 'A-30', 'L-18', 'CRIB O-4' should be
   replaced with their standard forms (A30, L18, O4).

3. DRILL KIT: The drills marked '<-- KIT' above are strong candidates for a
   standard drill kit based on WO volume across multiple parts.
""")
