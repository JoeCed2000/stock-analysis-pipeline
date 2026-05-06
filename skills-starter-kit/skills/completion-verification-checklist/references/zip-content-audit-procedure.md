# ZIP Content Audit — Concrete Procedure

## When to run

After any fix affecting the ZIP download endpoint (`/api/dossier/{ticker}/download` or similar).

## Procedure (copy-paste ready)

```bash
# Step 1: Download the ZIP from the live endpoint
curl -s -o /tmp/audit.zip "https://stock-analysis-api-tdtj.onrender.com/api/dossier/NVDA/download"

# Step 2: List ALL files with sizes
python3 -c "
import zipfile
zf = zipfile.ZipFile('/tmp/audit.zip', 'r')
for info in zf.infolist():
    print(f'{info.filename:65s} {info.file_size:>8,} bytes')
print(f'\nTotal: {len(zf.infolist())} files, {sum(i.file_size for i in zf.infolist()):,} bytes')
"

# Step 3: Extract and inspect file CONTENTS (not just existence)
python3 -c "
import zipfile, os, tempfile, shutil
zf = zipfile.ZipFile('/tmp/audit.zip', 'r')
tmp = tempfile.mkdtemp()
zf.extractall(tmp)

# Count sections with real content
sections = {}
for root, dirs, files in os.walk(tmp):
    for fn in files:
        fpath = os.path.join(root, fn)
        rel = os.path.relpath(fpath, tmp)
        section = rel.split('/')[0]
        size = os.path.getsize(fpath)
        is_placeholder = fn == 'README.txt' and size < 500
        if section not in sections:
            sections[section] = {'real': 0, 'placeholder': 0}
        if is_placeholder:
            sections[section]['placeholder'] += 1
        else:
            sections[section]['real'] += 1

for s in sorted(sections):
    r = sections[s]['real']
    p = sections[s]['placeholder']
    icon = '✅' if r > 0 else '⚠️'
    print(f'{icon} {s}: {r} real, {p} placeholder')

shutil.rmtree(tmp)
"
```

## Red flags

| Symptom | Meaning |
|---------|---------|
| File < 1KB with `.pdf` extension | Probably empty/converted from empty MD |
| Section has only `README.txt` | No real content generated for that section |
| Total ZIP < 10KB | Most sections are empty placeholders |
| `.md` files in ZIP | The ZIP filter is broken (should be PDF+XLSX only) |

## Case study (stock-analysis-pipeline, 2026-05-04)

Status endpoint showed `ready=true, files=20`. Declared "done." User said "dézippe et regarde."

ZIP audit revealed:
- 12 files, 25KB total
- Sections 02, 06: README.txt only (no real content)
- Sections 01, 03, 04, 05, 07: real PDFs/XLSX
- Verdict: 5/7 sections had content, not the claimed "7/7"

Root cause: `countDossierSections()` counted placeholder README.txt as valid sections. The status endpoint cached stale `files:[]` state. Both bugs now fixed.
