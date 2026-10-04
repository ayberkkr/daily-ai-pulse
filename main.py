import os
import sys
from datetime import datetime, timezone, timedelta
import requests

TRT = timezone(timedelta(hours=3))

def get_today_str():
    return datetime.now(TRT).strftime("%Y-%m-%d")

def get_today_display():
    return datetime.now(TRT).strftime("%d %B %Y, %H:%M TRT")

def clean_gh_repo(repo_val):
    if not repo_val:
        return None, None
    repo_val = repo_val.strip()
    if repo_val.startswith("https://github.com/"):
        name = repo_val.replace("https://github.com/", "").strip("/")
        return name, repo_val
    elif repo_val.startswith("http"):
        return repo_val, repo_val
    else:
        return repo_val, f"https://github.com/{repo_val}"

def fetch_hf_papers(limit=5):
    """Fetch top papers from Hugging Face Daily Papers."""
    url = "https://huggingface.co/api/daily_papers"
    headers = {"User-Agent": "DailyAIPulse/1.0 (+https://github.com/ayberkkr)"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        raw_papers = resp.json()
        
        # Sort by upvotes descending
        raw_papers.sort(key=lambda x: x.get("paper", {}).get("upvotes", 0), reverse=True)
        
        papers = []
        for item in raw_papers[:limit]:
            p = item.get("paper", {})
            arxiv_id = p.get("id", "")
            title = p.get("title", "").replace("\n", " ").strip()
            summary = p.get("summary", "").replace("\n", " ").strip()
            upvotes = p.get("upvotes", 0)
            
            raw_authors = p.get("authors", [])
            author_names = [a.get("name") for a in raw_authors if isinstance(a, dict) and a.get("name")]
            if len(author_names) > 3:
                authors_str = f"{', '.join(author_names[:3])} et al."
            elif author_names:
                authors_str = ", ".join(author_names)
            else:
                authors_str = "Unknown"

            gh_name, gh_url = clean_gh_repo(p.get("githubRepo"))
            gh_stars = p.get("githubStars")

            papers.append({
                "id": arxiv_id,
                "title": title,
                "summary": summary[:280] + "..." if len(summary) > 280 else summary,
                "authors": authors_str,
                "upvotes": upvotes,
                "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                "hf_url": f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else "",
                "github_repo_name": gh_name,
                "github_repo_url": gh_url,
                "github_stars": gh_stars,
            })
        return papers, raw_papers
    except Exception as e:
        print(f"[WARN] Failed to fetch Hugging Face papers: {e}", file=sys.stderr)
        return [], []

def fetch_trending_repos(raw_papers=None, limit=3):
    """Fetch active and trending AI/ML open-source repositories."""
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    query = f"topic:machine-learning+pushed:>{week_ago}+stars:>100"
    url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page={limit}"
    headers = {
        "User-Agent": "DailyAIPulse/1.0 (+https://github.com/ayberkkr)",
        "Accept": "application/vnd.github.v3+json"
    }
    
    gh_token = os.environ.get("GITHUB_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"
        
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        repos = []
        for repo in items[:limit]:
            repos.append({
                "full_name": repo.get("full_name"),
                "url": repo.get("html_url"),
                "description": repo.get("description") or "No description provided.",
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language") or "Python",
                "topics": repo.get("topics", [])[:4]
            })
        if repos:
            return repos
    except Exception as e:
        print(f"[WARN] GitHub Search API rate-limited or unavailable: {e}", file=sys.stderr)

    # Fallback: Extract verified open-source repos from today's top papers
    print("[INFO] Using verified open-source paper implementations as repository fallback.")
    fallback_repos = []
    if raw_papers:
        for item in raw_papers:
            p = item.get("paper", {})
            gh_raw = p.get("githubRepo")
            if gh_raw:
                name, url = clean_gh_repo(gh_raw)
                stars = p.get("githubStars") or 0
                title = p.get("title", "")
                fallback_repos.append({
                    "full_name": name,
                    "url": url,
                    "description": f"Official open-source implementation for: {title}",
                    "stars": stars,
                    "language": "Python",
                    "topics": ["research", "open-source", "paper-code"]
                })
                if len(fallback_repos) >= limit:
                    break
    return fallback_repos

def build_daily_report(date_str, display_date, papers, repos):
    lines = []
    lines.append(f"# 🧠 Daily AI Pulse — {date_str}\n")
    lines.append(f"> Automated research & open-source radar generated on **{display_date}**.\n")
    
    lines.append("## 📄 Featured AI/ML Research (ArXiv & Hugging Face)\n")
    if not papers:
        lines.append("_Bugün için öne çıkan makale verisi alınamadı veya liste güncelleniyor._\n")
    else:
        for idx, p in enumerate(papers, 1):
            lines.append(f"### {idx}. [{p['title']}]({p['arxiv_url'] or p['hf_url']})")
            lines.append(f"- **Yazarlar:** {p['authors']}")
            lines.append(f"- **Topluluk Beğenisi:** 🔥 `{p['upvotes']} upvotes`")
            if p.get('github_repo_url'):
                star_info = f" (★ {p['github_stars']})" if p.get('github_stars') else ""
                lines.append(f"- **Açık Kaynak Kod:** [{p['github_repo_name']}]({p['github_repo_url']}){star_info}")
            lines.append(f"- **Özet:** {p['summary']}")
            lines.append(f"- **Bağlantılar:** [arXiv]({p['arxiv_url']}) • [Hugging Face Discussion]({p['hf_url']})\n")

    lines.append("## ⚡ Trending Open-Source AI Repositories\n")
    if not repos:
        lines.append("_Bugün için trend repo verisi alınamadı._\n")
    else:
        for r in repos:
            topics_badge = " ".join([f"`#{t}`" for t in r['topics']])
            lines.append(f"### 📦 [{r['full_name']}]({r['url']})")
            lines.append(f"- **Yıldız Sayısı:** ⭐ `{r['stars']:,}` | **Dil:** `{r['language']}`")
            lines.append(f"- **Açıklama:** {r['description']}")
            if topics_badge:
                lines.append(f"- **Etiketler:** {topics_badge}")
            lines.append("")

    lines.append("---\n")
    lines.append("*Bu rapor [Daily AI Pulse](https://github.com/ayberkkr/daily-ai-pulse) GitHub Action otomasyonu tarafından her gün saat 12:00 TRT'de derlenir.*")
    return "\n".join(lines)

def update_readme(latest_report_file, date_str, display_date, papers, repos):
    reports_dir = "reports"
    report_files = []
    if os.path.exists(reports_dir):
        report_files = sorted([f for f in os.listdir(reports_dir) if f.endswith(".md")], reverse=True)

    lines = []
    lines.append("# 🧠 Daily AI Pulse")
    lines.append("\n> **Yapay Zeka ve Makine Öğrenimi (AIML)** literatürünü ve açık kaynak AI dünyasını her gün saat 12:00'de (TRT) otonom olarak tarayan günlük bülten ve veri boru hattı.\n")
    lines.append("[![Daily Pulse](https://github.com/ayberkkr/daily-ai-pulse/actions/workflows/daily-pulse.yml/badge.svg)](https://github.com/ayberkkr/daily-ai-pulse/actions/workflows/daily-pulse.yml)")
    lines.append("![License](https://img.shields.io/badge/License-MIT-blue.svg)")
    lines.append(f"![Last Updated](https://img.shields.io/badge/Son%20G%C3%BCncelleme-{date_str}-amber)\n")

    lines.append(f"## 🚀 Günün Radarı ({date_str})")
    lines.append(f"> En son güncelleme: **{display_date}** | [Tüm Raporu Oku →]({latest_report_file})\n")

    if papers:
        lines.append("### 📄 Öne Çıkan AI Makaleleri")
        for p in papers[:3]:
            lines.append(f"- **[{p['title']}]({p['arxiv_url']})** — `{p['upvotes']} upvotes` ({p['authors']})")
        lines.append("")

    if repos:
        lines.append("### ⚡ Trend Açık Kaynak Projeleri")
        for r in repos[:3]:
            lines.append(f"- **[{r['full_name']}]({r['url']})** (⭐ `{r['stars']:,}`) — {r['description']}")
        lines.append("")

    lines.append("## 📚 Arşiv")
    lines.append("| Tarih | Rapor |")
    lines.append("| :--- | :--- |")
    for f in report_files[:30]:
        d = f.replace(".md", "")
        lines.append(f"| {d} | [Raporu İncele](reports/{f}) |")

    lines.append("\n---\n")
    lines.append("### ⚙️ Nasıl Çalışır?")
    lines.append("1. **Hugging Face Daily Papers API** üzerinden yapay zeka topluluğunun o gün en çok oy verdiği akademik makaleleri toplar.")
    lines.append("2. **GitHub Search API** ile son 7 günün en aktif ve yüksek yıldızlı açık kaynak AI/ML projelerini tespit eder.")
    lines.append("3. **GitHub Actions** ile her gün saat **12:00 TRT (09:00 UTC)**'de sıfır insan müdahalesiyle derlenip depoya commit edilir.\n")

    lines.append("Developed by [Ayberk Kar](https://github.com/ayberkkr) • Bursa Teknik Üniversitesi AIML")

    return "\n".join(lines)

def main():
    date_str = get_today_str()
    display_date = get_today_display()
    print(f"[INFO] Running Daily AI Pulse for {date_str}...")

    papers, raw_papers = fetch_hf_papers(limit=5)
    print(f"[INFO] Fetched {len(papers)} papers from Hugging Face.")

    repos = fetch_trending_repos(raw_papers=raw_papers, limit=3)
    print(f"[INFO] Fetched {len(repos)} trending repositories.")

    os.makedirs("reports", exist_ok=True)
    report_filename = os.path.join("reports", f"{date_str}.md")
    report_content = build_daily_report(date_str, display_date, papers, repos)

    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"[INFO] Wrote report to {report_filename}")

    readme_content = update_readme(report_filename.replace("\\", "/"), date_str, display_date, papers, repos)
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("[INFO] Updated README.md")

if __name__ == "__main__":
    main()
