# AI Search Observability — ชุดทดลอง 3 วัน

เครื่องมือวัดว่า AI search พูดถึง / แนะนำ / อ้างอิงธุรกิจของเราแค่ไหน และตอบ 3 คำถามที่ต้องรู้ก่อนเลือกหัวข้อ:

1. **Day 1** ผลนิ่งพอจะวัดไหม และต้องยิงกี่รอบ
2. **Day 2** สิ่งที่วัดผ่าน API ตรงกับที่ลูกค้าเห็นในแอปจริงไหม
3. **Day 3** ร้านที่แพ้ แพ้เพราะอะไร (ดูจากหน้าที่ AI อ้างอิงจริง)

ไม่ต้องติดตั้ง library เพิ่ม ใช้แค่ Python 3.10 ขึ้นไป

---

## ⚠️ เรื่อง API key

- **ห้ามวาง key ในแชท ห้ามใส่ในโค้ด ห้าม commit ขึ้น GitHub**
- โปรแกรมอ่าน key จากตัวแปร environment `GEMINI_API_KEY` เท่านั้น ไม่พิมพ์ออกจอ ไม่บันทึกลงไฟล์
- `.gitignore` กัน `config.json`, `data/`, `.env` ไว้ให้แล้ว
- ถ้าเผลอหลุด ให้ลบ key ทิ้งใน Google AI Studio แล้วสร้างใหม่ทันที

---

## 1. ลองแบบไม่ใช้ key ก่อน (ฟรี 100%)

มี provider จำลองชื่อ `mock` ให้ลองเดินครบทุกขั้นโดยไม่เสียอะไร

```bash
cd aiso-kit
cp config.example.json config.json
python3 -m aiso.collect --provider mock --smoke
python3 -m aiso.collect --provider mock --mode fixed --repeats 10 --rpm 0
python3 -m aiso.collect --provider mock --mode adaptive --focus target --rpm 0
python3 -m aiso.report
```

เปิดดู `reports/report_<วันที่>.md` จะเห็นหน้าตารายงานทั้งหมด แล้ว **ลบข้อมูลจำลองทิ้งก่อนเริ่มของจริง**

```bash
rm -rf data reports        # Windows: rmdir /s /q data reports
```

## 2. ตั้งค่า key

macOS / Linux
```bash
export GEMINI_API_KEY="...."
```
Windows (PowerShell)
```powershell
$env:GEMINI_API_KEY="...."
```
ต้องตั้งใหม่ทุกครั้งที่เปิด terminal ใหม่

## 3. เช็กว่า key ใช้ได้ (1 request)

```bash
python3 -m aiso.collect --smoke --no-search   # free tier ใช้ได้
python3 -m aiso.collect --smoke               # มี Google Search (ต้องเปิด billing)
```

ควรเห็นคำตอบ (+ รายชื่อ citation ถ้าใช้ search) ถ้า error

- `HTTP 404` → ชื่อโมเดลเปลี่ยนแล้ว ดูชื่อล่าสุดใน Google AI Studio แล้วใส่ `--model ชื่อใหม่` (default ตอนนี้ `gemini-3.8-flash`)
- `HTTP 400/403` → key ผิด หรือยังไม่ได้เปิดใช้ API
- `HTTP 429` มี 2 แบบ
  - ข้อความมี `exceeded your current quota` → ไม่มี quota สำหรับโมเดล/ฟีเจอร์นี้ (เช่น google_search ใน free tier) โปรแกรมหยุดทันทีเพราะ retry ไม่ช่วย → ใช้ `--no-search` หรือเปิด billing
  - แบบอื่น → ยิงเร็วเกิน โปรแกรมรอแล้วลองใหม่ให้อัตโนมัติ ถ้ายังไม่หายให้ลด `--rpm`

### search vs no-search

| | มี search (default) | `--no-search` |
|---|---|---|
| ชื่อ provider ในข้อมูล/รายงาน | `gemini` | `gemini_nosearch` |
| ข้อมูลมาจาก | ผลค้นเว็บจริงตอนนั้น | ความรู้ในตัวโมเดล (ไม่อัปเดต) |
| citations | มี | ไม่มี (cited จะเป็น 0 เสมอ) |
| free tier | ไม่ได้ (429 quota) | ได้ |
| ใช้วัด "AI search" จริงได้ไหม | ได้ | ไม่ได้ — ใช้ทดสอบ pipeline/เทียบเป็น baseline เท่านั้น |

ข้อมูลสองแบบถูกแยกกันในรายงานเสมอ ไม่ต้องกลัวปนกัน

## 4. แก้ config.json เป็นธุรกิจจริง

- `target` = ร้านที่เราสนใจ
- `competitors` = คู่แข่งที่รู้จัก (ไม่ต้องครบ รายงานจะบอกชื่อที่ AI พูดถึงแต่คุณยังไม่ได้ใส่)
- `aliases` = ชื่อเรียกอื่น ทั้งไทย อังกฤษ สะกดแบบที่คนชอบเขียน **ส่วนนี้สำคัญมาก** ถ้าไม่ครบ ระบบจะนับไม่เจอ
- `domains` = เว็บ/เพจของร้าน ใช้ตรวจว่าถูกอ้างอิงไหม
- `queries` = คำถามที่ลูกค้าน่าจะถามจริง 10 ข้อ ระบุทำเลในคำถามเสมอ

---

## Day 1 — ผลนิ่งไหม + ต้องยิงกี่รอบ

```bash
python -m aiso.collect --mode fixed --repeats 10                    # 100 requests, ~13 นาที
python -m aiso.collect --mode adaptive --focus target              # ~60-90 requests
python -m aiso.report
```

ดูในรายงาน **ข้อ 1**

- ความเหมือนเฉลี่ย ≥ 60% → สัญญาณนิ่งพอวัด ✅
- ตาราง "ต้องยิงกี่รอบ" → ใช้กำหนดงบประมาณทั้งโปรเจกต์
- Adaptive vs Fixed → ประหยัดได้กี่ % และตัวเลขเพี้ยนไปเท่าไหร่ ← **นี่คือ research finding ข้อแรกของคุณ**

> ถ้าอยากรู้ว่า "ต่างกันตามธรรมชาติ" เท่าไหร่ ให้รัน fixed ซ้ำอีกรอบในวันเดียวกัน แล้วเทียบ fixed กับ fixed นั่นคือเส้นฐานที่ adaptive ควรถูกวัดเทียบ

**วันถัดไปให้รัน fixed อีกรอบ (เช่น `--repeats 5`)** รายงานจะแยกให้ว่าความแกว่งมาจาก "ภายในวัน" หรือ "ข้ามวัน"

## Day 2 — API ตรงกับแอปไหม

เปิดแอป Gemini ในมือถือ ถามทีละคำถามตาม config แล้ว copy คำตอบมาวาง

```bash
python -m aiso.manual --provider gemini
```

วางคำตอบ → พิมพ์ `END` บรรทัดใหม่ (ข้ามได้ด้วย `SKIP`) ลิงก์ที่ขึ้นต้นด้วย http จะถูกเก็บเป็น citation

เก็บ web engine อื่นด้วยมือ (Gemini / ChatGPT / Perplexity / AI Mode) ให้ทำตาม **`docs/run-sheet.md`** และสร้าง checklist ด้วย

```bash
python -m aiso.runsheet --repeats 3 --out reports/runsheet        # checklist .md + .csv
python -m aiso.manual --provider chatgpt --repeat 0 --queries 1-5 --who TN --note "Chrome incognito, logged-out, Bangkok"
python -m unittest discover -s tests                              # ทดสอบ parser (ไม่ใช้ network)
```

ดูรายงาน **ข้อ 2** ถ้าตรงกันน้อย ไม่ได้แปลว่าโปรเจกต์ล้ม มันคือ finding ที่ต้องเขียนเป็นข้อจำกัด (และน่าสนใจด้วย)

## Day 3 — Why Not Me?

รายงาน **ข้อ 4** จะลิสต์ query ที่ร้านเราแพ้ พร้อมหน้าที่ AI อ้างอิงบ่อย ให้เปิดอ่านจริงแล้วจดในช่อง `________` ว่าหน้าพวกนั้นมีข้อมูลอะไรที่เว็บเราไม่มี

**ถ้าคุณดูเองแล้วยังมองไม่ออก = ระบบอัตโนมัติก็จะหาไม่เจอ** นี่คือด่านตัดสินว่าหัวข้อไปรอดไหม

## ตรวจว่าตัวนับแม่นไหม (ทำก่อนเชื่อตัวเลขใด ๆ)

```bash
python -m aiso.label --n 50
```

อ่านคำตอบแล้วพิมพ์เลขร้านที่ถูกพูดถึง / ถูกแนะนำ (หยุดกลางทางได้ ทำต่อทีหลังได้) รายงาน **ข้อ 5** จะบอก precision/recall

ถ้า `recommended` แม่นต่ำกว่า ~80% ให้ปรับคำใน `REC_MARKERS` ใน `aiso/extract.py`

---

## ค่าใช้จ่ายและเพดาน

- ค่าเริ่มต้นยิงไม่เกิน **8 ครั้ง/นาที** และไม่เกิน **150 ครั้งต่อการรัน 1 ครั้ง** เปลี่ยนได้ด้วย `--rpm` และ `--max-requests`
- ข้อมูลบันทึกลงดิสก์ทันทีทุก request ไฟดับหรือกด Ctrl+C ก็ไม่เสียของที่เก็บแล้ว
- free tier และการใช้ Google Search grounding อาจมีลิมิตรายวันแยกต่างหาก และเปลี่ยนบ่อย **เช็กหน้า pricing/rate limits ใน Google AI Studio ก่อนรันจริง**
- แก้ config แล้วรันรายงานใหม่ได้ฟรี ไม่ต้องยิงใหม่

## ข้อจำกัดที่รู้อยู่แล้ว

- URL ใน citation ของ Gemini มักเป็นลิงก์ redirect ของ Google ส่วน **title** มักเป็นชื่อโดเมน ระบบจึงตรวจทั้งคู่
- รูปแบบ response ของ API อาจเปลี่ยนในอนาคต ถ้า smoke test ได้คำตอบว่างเปล่า แก้ที่ `GeminiProvider._parse` ใน `aiso/providers.py`
- การจับชื่อเป็นแบบ substring ชื่อสั้นมาก ๆ อาจนับเกิน ใช้ `label.py` วัดเสมอ
- API ไม่มีพิกัดผู้ใช้ จึงต้องใส่ทำเลในคำถาม (ระบุเป็นข้อจำกัดในรายงาน)

## Tests

ชุดทดสอบใช้ `unittest` ของ stdlib (ไม่ต้องติดตั้งอะไรเพิ่ม ไม่ยิง network ไม่ต้องมี `GEMINI_API_KEY`)

```bash
python -m unittest discover -s tests
```

ครอบคลุม `stats.py` (Wilson CI, Jaccard, required_n, variance), กติกาหยุดของ adaptive (`should_stop`),
การจับชื่อ/citation (`entities.py`), mentioned/cited/recommended + การตัด source chip (`extract.py`)
และ end-to-end บน mock provider (fixed vs adaptive) ในโฟลเดอร์ชั่วคราว ไม่แตะ `data/` หรือ `reports/`
GitHub Actions รันชุดนี้บน Python 3.10 และ 3.12 (`.github/workflows/tests.yml`)

## โครงสร้างโค้ด (อ่านตามลำดับนี้)

| ไฟล์ | ทำอะไร |
|---|---|
| `aiso/stats.py` | สถิติทั้งหมด (Wilson CI, Jaccard, จำนวนรอบที่ต้องใช้, variance) — อาจารย์จะถามตรงนี้ |
| `aiso/entities.py` | จับชื่อร้านไทย/อังกฤษ และหาชื่อคู่แข่งที่ไม่รู้จัก |
| `aiso/extract.py` | ตัดสินว่า mentioned / cited / recommended |
| `aiso/providers.py` | ต่อ Gemini (และ mock) — เพิ่มเจ้าอื่นได้ด้วยการเขียน class ใหม่ |
| `aiso/collect.py` | ยิง query, rate limit, retry, เพดาน, adaptive sampling |
| `aiso/report.py` | สร้างรายงาน Day 1/2/3 |
| `aiso/manual.py` / `aiso/label.py` | เก็บคำตอบจากแอป / label มือ |

---

## MVP demo (ต.ค. 2026) — สำหรับนำเสนออาจารย์

ติดตั้งครั้งเดียว (Playwright + Chromium อยู่ใน `.venv`)

```bash
uv venv .venv && uv pip install --python .venv/bin/python playwright
.venv/bin/python -m playwright install chromium
```

Live demo: ถาม Perplexity 1 ครั้ง (เปิดเบราว์เซอร์ให้เห็น) แล้วสร้าง dashboard

```bash
.venv/bin/python -m aiso.collect --provider perplexity_web --smoke --rpm 0
.venv/bin/python -m aiso.dashboard        # -> reports/dashboard.html
open reports/dashboard.html
```

เก็บตัวอย่างจริงชุดเล็ก (5 queries × 3 รอบ ≈ 8 นาที)

```bash
.venv/bin/python -m aiso.collect --provider perplexity_web --repeats 3 --limit-queries 5 --rpm 2 --max-requests 20
```

| engine | provider name | สถานะ |
|---|---|---|
| Perplexity (web) | `perplexity_web` | automated (Playwright) |
| Gemini / ChatGPT / AI Mode (web) | `gemini_web` `chatgpt_web` `aimode_web` | stub → ใช้ `python -m aiso.manual` |
| Gemini API ไม่มี search | `gemini --no-search` | baseline |

กติกา: เจอหน้า login หรือ CAPTCHA โปรแกรมหยุดทันที ไม่ retry ไม่หาทางเลี่ยง

ภาพอธิบายการทำงานทั้งระบบ (มี animation): `docs/how-it-works.html`
