"""세레스 랭킹 수집기 (GitHub Actions용, 상태 저장 서버 불필요).
docs/data/latest.json  : 최신 전체+무기별 랭킹, 무기 등록 수
docs/data/history.json : 매 수집 시각의 전체 랭킹(닉네임→[순위,레벨])과 무기 수 기록"""
import json, os, re, time
from urllib.parse import unquote
import requests
from bs4 import BeautifulSoup

URL = "https://seresonline.co.kr/ranking"
TABS = {"all": "", "sword": "wpn:sword", "greatsword": "wpn:greatsword", "spear": "wpn:spear",
        "dagger": "wpn:dagger", "bow": "wpn:bow", "wand": "wpn:wand", "scythe": "wpn:scythe",
        "knuckle": "wpn:knuckle", "gun": "wpn:gun",
        "mining": "life:mining", "gathering": "life:gathering", "fishing": "life:fishing",
        "smithing": "life:smithing", "alchemy": "life:alchemy", "cooking": "life:cooking",
        "blacksmith": "prof:blacksmith", "gatherer": "prof:gatherer", "alchemist": "prof:alchemist", "chef": "prof:chef"}
OUT = "docs/data"
J = dict(ensure_ascii=False, separators=(",", ":"))

def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    life = "생활레벨" in html
    for tr in soup.select("table tr"):
        c = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(c) >= 6 and c[1].isdigit():   # 1~3위는 메달 이모지 → 순서로 순위 계산
            if life:   # 생활 레벨 탭: [생활레벨, 닉네임, 유저레벨, 직업, 길드] (닉네임이 비공개면 빈 문자열)
                rows.append([int(c[1]), c[2], int(c[3] or 0), c[4], c[5]])
            else:      # 일반 탭: [레벨, 닉네임, 직업, 길드, 도달 층]
                rows.append([int(c[1]), c[2], c[3], c[4], int(re.sub(r"\D", "", c[5]) or 0)])
    text = soup.get_text(" ")
    counts = {w: int(n) for w, n in re.findall(r"(한손검|대검|창|단검|활|완드|낫|건틀릿|마도총|채광|채집가|채집|낚시|제련|연금사|연금|요리사|요리|대장장이)\s*\((\d+)\)", text)}
    names = {"wpn:sword": "한손검", "wpn:greatsword": "대검", "wpn:spear": "창", "wpn:dagger": "단검", "wpn:bow": "활",
             "wpn:wand": "완드", "wpn:scythe": "낫", "wpn:knuckle": "건틀릿", "wpn:gun": "마도총",
             "life:mining": "채광", "life:gathering": "채집", "life:fishing": "낚시", "life:smithing": "제련",
             "life:alchemy": "연금", "life:cooking": "요리", "prof:blacksmith": "대장장이", "prof:gatherer": "채집가",
             "prof:alchemist": "연금사", "prof:chef": "요리사"}
    for a_ in soup.find_all(["a", "button"]):       # 탭 버튼/링크 안의 숫자 = 등록 수
        mm = re.search(r"job=([^&#]+)", unquote(a_.get("href", "") or ""))
        n_ = re.search(r"\d[\d,]*", a_.get_text(" "))
        if mm and mm.group(1) in names and n_:
            counts[names[mm.group(1)]] = int(n_.group(0).replace(",", ""))
    m = re.search(r"(\d+월\s*\d+일\s*\d+:\d+)\s*기준", text)
    return rows, counts, m.group(1) if m else ""

def main():
    os.makedirs(OUT, exist_ok=True)
    lp = f"{OUT}/latest.json"
    prev = json.load(open(lp, encoding="utf-8"))["tabs"] if os.path.exists(lp) else {}
    tabs, counts, base = {}, {}, ""
    for key, tab in TABS.items():
        r = requests.get(URL, params={"job": tab} if tab else None,
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        rows, c, b = parse(r.text)
        if key == "all" and not rows:
            raise SystemExit("표를 읽지 못했습니다(사이트 구조 변경 또는 JS 렌더링 가능성). 응답 앞부분: " + re.sub(r"\s+", " ", r.text[:300]))
        tabs[key] = rows
        if key == "all":
            counts, base = c, b
        elif b != base:                      # 기준 시각이 다른 탭(오래된 사본)은 이전 데이터를 유지
            print(f"경고: {key} 기준 시각 불일치({b} != {base}) → 이전 데이터 유지")
            tabs[key] = prev.get(key, [])
        time.sleep(2)
    if not tabs["all"]:
        raise SystemExit("빈 응답")
    hp = f"{OUT}/history.json"
    H = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else {"snaps": []}
    if H["snaps"] and H["snaps"][-1].get("base") == base:
        print("새 갱신 없음:", base); return    # 사이트가 아직 갱신 전이면 중복 기록 방지
    ts = int(time.time())
    json.dump({"ts": ts, "base": base, "tabs": tabs, "counts": counts}, open(f"{OUT}/latest.json", "w", encoding="utf-8"), **J)
    ranks = {n: [i + 1, lv] for i, (lv, n, *_) in enumerate(tabs["all"])}
    jm = {r[1]: r[2] for r in tabs["all"]}          # 닉네임 → 직업 (전체 랭킹)
    seen = set()
    for k in ("sword", "greatsword", "spear", "dagger", "bow", "wand", "scythe", "knuckle", "gun"):
        for r in tabs.get(k, []):                   # 무기 랭킹에 처음 나온 직업을 우선(화면과 같은 규칙)
            if r[1] not in seen:
                seen.add(r[1]); jm[r[1]] = r[2]
    jobs = {}
    for j in jm.values():
        jobs[j] = jobs.get(j, 0) + 1
    snap = {"ts": ts, "base": base, "counts": counts, "ranks": ranks, "jobs": jobs}
    if len(H["snaps"]) % 6 == 0:   # 6시간마다: 전체 랭킹 밖 무기 랭킹 플레이어의 레벨도 기록(성장 속도용)
        ex = {}
        for k in ("sword", "greatsword", "spear", "dagger", "bow", "wand", "scythe", "knuckle", "gun"):
            for lv, n, *_ in tabs.get(k, []):
                if n not in ranks:
                    ex[n] = lv
        snap["lv"] = ex
    H["snaps"].append(snap)
    H["snaps"] = H["snaps"][-1100:]           # 약 45일치
    json.dump(H, open(hp, "w", encoding="utf-8"), **J)
    build_standalone(json.load(open(f"{OUT}/latest.json", encoding="utf-8")), H)
    print("저장:", base, len(H["snaps"]))

def build_standalone(latest, hist):
    """docs/standalone.html: 데이터가 안에 들어간 단일 파일. 더블클릭만 하면 열려요(서버·GitHub 불필요)."""
    html = open("docs/index.html", encoding="utf-8").read()
    data = json.dumps({"latest": latest, "history": hist}, **J).replace("</", "<\\/")
    marker = '<script>window.addEventListener("error"'
    html = html.replace(marker, "<script>window.__DATA__=" + data + ";</script>\n" + marker, 1)
    open("docs/standalone.html", "w", encoding="utf-8").write(html)

if __name__ == "__main__":
    main()
