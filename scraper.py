import json
import os
import re
import time
import base64
import html as html_mod
import logging
import urllib.request
import urllib.parse
import ssl
from datetime import datetime

from classifier import classify_job

logger = logging.getLogger(__name__)

WORKDAY_QUERIES = [
    "Graduate Engineer Trainee", "Graduate Trainee", "Engineering Trainee",
    "Trainee Engineer", "Fresher", "Graduate Engineer", "Entry Level Engineer",
    "Software Engineer", "Data Engineer", "Mechanical Engineer",
    "Electrical Engineer", "Civil Engineer", "Electronics Engineer",
]

ADZUNA_QUERIES = [
    "graduate engineer trainee", "graduate trainee", "engineering trainee",
    "trainee engineer fresher", "fresher engineer", "GET fresher",
    "software trainee", "mechanical engineer fresher",
    "electrical engineer fresher", "civil engineer fresher",
]

JOOBLE_QUERIES = [
    "graduate engineer trainee India", "graduate trainee India",
    "engineering trainee fresher India", "trainee engineer India",
    "fresher mechanical engineer India", "fresher electrical engineer India",
    "fresher civil engineer India", "fresher software engineer India",
]

LINKEDIN_QUERIES = [
    "graduate engineer trainee india", "graduate trainee india",
    "engineering trainee india", "trainee engineer india",
    "fresher engineer india", "get trainee india",
]


class BaseScraper:
    def __init__(self):
        self.ctx = ssl.create_default_context()

    def _get_json(self, url, timeout=20):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=self.ctx, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get_html(self, url, timeout=20):
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, context=self.ctx, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")


class WorkdayScraper(BaseScraper):
    def __init__(self, sites):
        super().__init__()
        self.sites = sites

    def scrape_site(self, site):
        api_url = f"https://{site['slug']}.{site['subdomain']}.myworkdayjobs.com/wday/cxs/{site['slug']}/{site['site_path']}/jobs"
        api_base = f"https://{site['slug']}.{site['subdomain']}.myworkdayjobs.com/en-US/{site['site_path']}"
        all_jobs, seen = [], set()

        for query in WORKDAY_QUERIES:
            offset, no_new_streak = 0, 0
            while no_new_streak < 2:
                try:
                    payload = json.dumps({
                        "appliedFacets": {}, "limit": 20, "offset": offset,
                        "searchText": query,
                    }).encode("utf-8")
                    req = urllib.request.Request(api_url, data=payload, headers={
                        "Content-Type": "application/json", "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0",
                    }, method="POST")
                    with urllib.request.urlopen(req, context=self.ctx, timeout=30) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    jobs = data.get("jobPostings", [])
                    if not jobs:
                        break
                    new_count = 0
                    for j in jobs:
                        jid = j.get("externalPath", j.get("title", ""))
                        if jid in seen:
                            continue
                        seen.add(jid)
                        all_jobs.append({
                            "id": f"workday|{site['name']}|{jid}",
                            "title": j.get("title", ""),
                            "company": site["name"],
                            "location": j.get("locationsText", "N/A"),
                            "posted": j.get("postedOn", "N/A"),
                            "url": api_base + jid if jid else "",
                            "source": f"Workday:{site['name']}",
                            "description": "",
                        })
                        new_count += 1
                    no_new_streak = no_new_streak + 1 if new_count == 0 else 0
                    offset += 20
                    time.sleep(0.2)
                except Exception as e:
                    logger.error(f"Workday {site['name']} error: {e}")
                    break
            time.sleep(0.3)
        return all_jobs


class GreenhouseScraper(BaseScraper):
    def __init__(self, companies):
        super().__init__()
        self.companies = companies

    def scrape(self):
        jobs = []
        for c in self.companies:
            try:
                data = self._get_json(
                    f"https://boards-api.greenhouse.io/v1/boards/{c['board']}/jobs?content=true"
                )
                for j in data.get("jobs", []):
                    desc = j.get("content", "") or ""
                    if desc:
                        try:
                            desc = base64.b64decode(desc.encode("ascii", errors="ignore")).decode("utf-8", errors="ignore")
                            desc = re.sub(r"<[^>]+>", " ", desc)
                        except Exception:
                            desc = ""
                    jobs.append({
                        "id": f"greenhouse|{c['name']}|{j.get('id', '')}",
                        "title": j.get("title", ""),
                        "company": c["name"],
                        "location": (j.get("location") or {}).get("name", "N/A"),
                        "posted": (j.get("updated_at", "") or "N/A")[:10],
                        "url": j.get("absolute_url", ""),
                        "source": f"Greenhouse:{c['name']}",
                        "description": desc[:3000],
                    })
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"Greenhouse {c['name']} error: {e}")
        return jobs


class LeverScraper(BaseScraper):
    def __init__(self, companies):
        super().__init__()
        self.companies = companies

    def scrape(self):
        jobs = []
        for c in self.companies:
            try:
                data = self._get_json(f"https://api.lever.co/v0/postings/{c['board']}?mode=json")
                for j in data:
                    cats = j.get("categories") or {}
                    loc = j.get("workplaceType", "") or cats.get("location", "N/A")
                    desc = j.get("description", "") or ""
                    for lst in j.get("lists") or []:
                        content = lst.get("content") or []
                        if isinstance(content, str):
                            desc += " " + content
                        else:
                            for item in content:
                                desc += " " + (item if isinstance(item, str) else item.get("content", ""))
                    desc = re.sub(r"<[^>]+>", " ", html_mod.unescape(desc))
                    ts = j.get("createdAt", 0)
                    posted = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "N/A"
                    jobs.append({
                        "id": f"lever|{c['name']}|{j.get('id', '')}",
                        "title": j.get("text", ""),
                        "company": c["name"],
                        "location": loc or "N/A",
                        "posted": posted,
                        "url": j.get("hostedUrl", ""),
                        "source": f"Lever:{c['name']}",
                        "description": desc[:3000],
                    })
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"Lever {c['name']} error: {e}")
        return jobs


class SmartRecruitersScraper(BaseScraper):
    def __init__(self, companies):
        super().__init__()
        self.companies = companies

    def scrape(self):
        jobs = []
        for c in self.companies:
            try:
                data = self._get_json(
                    f"https://api.smartrecruiters.com/v1/companies/{c['board']}/postings?limit=100"
                )
                for j in data.get("content", []):
                    loc = j.get("location", {}) or {}
                    remote = j.get("remote", False)
                    loc_str = ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")])) or ("Remote" if remote else "N/A")
                    released = (j.get("releasedDate", "") or "N/A")[:10]
                    jobs.append({
                        "id": f"smartrec|{c['name']}|{j.get('id', '')}",
                        "title": j.get("name", ""),
                        "company": c["name"],
                        "location": loc_str,
                        "posted": released,
                        "url": f"https://jobs.smartrecruiters.com/{c['board']}/{j.get('id', '')}",
                        "source": f"SmartRecruiters:{c['name']}",
                        "description": (j.get("description", "") or "")[:2000] if isinstance(j.get("description"), str) else "",
                    })
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"SmartRecruiters {c['name']} error: {e}")
        return jobs


class AshbyScraper(BaseScraper):
    def __init__(self, companies):
        super().__init__()
        self.companies = companies

    def scrape(self):
        jobs = []
        for c in self.companies:
            try:
                data = self._get_json(f"https://api.ashbyhq.com/posting-api/job-board/{c['board']}")
                for j in data.get("jobs", []):
                    jobs.append({
                        "id": f"ashby|{c['name']}|{j.get('id', '')}",
                        "title": j.get("title", ""),
                        "company": c["name"],
                        "location": j.get("location", "") or j.get("workplaceType", "N/A"),
                        "posted": (j.get("publishedAt", "") or "N/A")[:10],
                        "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                        "source": f"Ashby:{c['name']}",
                        "description": re.sub(r"<[^>]+>", " ", j.get("descriptionHtml", "") or "")[:3000],
                    })
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"Ashby {c['name']} error: {e}")
        return jobs


class AdzunaScraper(BaseScraper):
    def __init__(self, app_id, app_key):
        self.app_id = app_id
        self.app_key = app_key
        super().__init__()
        self.available = bool(app_id and app_key)

    def scrape(self):
        if not self.available:
            return []
        jobs = []
        for q in ADZUNA_QUERIES:
            try:
                url = (
                    f"https://api.adzuna.com/v1/api/jobs/in/search/1"
                    f"?app_id={self.app_id}&app_key={self.app_key}"
                    f"&q={urllib.parse.quote(q)}&results_per_page=50"
                    f"&max_days_old=14&content-type=application/json"
                )
                data = self._get_json(url, timeout=15)
                for j in data.get("results", []):
                    jobs.append({
                        "id": f"adzuna|{j.get('id', '')}",
                        "title": re.sub(r"<[^>]+>", "", j.get("title", "")),
                        "company": (j.get("company") or {}).get("display_name", "Unknown"),
                        "location": (j.get("location") or {}).get("display_name", ""),
                        "posted": j.get("created", ""),
                        "url": j.get("redirect_url", ""),
                        "source": "Adzuna",
                        "description": (j.get("description", "") or "")[:2000],
                    })
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Adzuna error: {e}")
        return jobs


class JoobleScraper(BaseScraper):
    def __init__(self, api_key):
        self.api_key = api_key
        super().__init__()
        self.available = bool(api_key)

    def scrape(self):
        if not self.available:
            return []
        jobs = []
        for q in JOOBLE_QUERIES:
            try:
                payload = json.dumps({"keywords": q, "page": 1, "count": 50}).encode("utf-8")
                req = urllib.request.Request("https://jooble.org/api/", data=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": self.api_key,
                    "User-Agent": "Mozilla/5.0",
                }, method="POST")
                with urllib.request.urlopen(req, context=self.ctx, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for j in data.get("jobs", []):
                    jobs.append({
                        "id": f"jooble|{j.get('id', '')}",
                        "title": j.get("title", ""),
                        "company": j.get("company", "Unknown"),
                        "location": j.get("location", ""),
                        "posted": j.get("date", ""),
                        "url": j.get("link", ""),
                        "source": "Jooble",
                        "description": (j.get("snippet", "") or "")[:2000],
                    })
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Jooble error: {e}")
        return jobs


class RemotiveScraper(BaseScraper):
    def scrape(self):
        jobs = []
        try:
            data = self._get_json("https://remotive.com/api/remote-jobs?limit=100", timeout=15)
            for j in data.get("jobs", []):
                jobs.append({
                    "id": f"remotive|{j.get('id', '')}",
                    "title": j.get("title", ""),
                    "company": j.get("company_name", "Unknown"),
                    "location": j.get("candidate_required_location", "Remote"),
                    "posted": j.get("publication_date", ""),
                    "url": j.get("url", ""),
                    "source": "Remotive",
                    "description": re.sub(r"<[^>]+>", " ", j.get("description", "") or "")[:2000],
                })
        except Exception as e:
            logger.error(f"Remotive error: {e}")
        return jobs


class ArbeitnowScraper(BaseScraper):
    def scrape(self):
        jobs = []
        try:
            data = self._get_json("https://arbeitnow.com/api/job-board-api", timeout=15)
            for j in data.get("data", []):
                jobs.append({
                    "id": f"arbeitnow|{j.get('id', '')}",
                    "title": j.get("title", ""),
                    "company": j.get("company_name", "Unknown"),
                    "location": j.get("location", ""),
                    "posted": j.get("created_at", ""),
                    "url": j.get("url", j.get("application_url", "")),
                    "source": "Arbeitnow",
                    "description": re.sub(r"<[^>]+>", " ", j.get("description", "") or "")[:2000],
                })
        except Exception as e:
            logger.error(f"Arbeitnow error: {e}")
        return jobs


class RemoteOKScraper(BaseScraper):
    def scrape(self):
        jobs = []
        try:
            data = self._get_json("https://remoteok.com/api", timeout=15)
            for j in data:
                if not isinstance(j, dict) or "id" not in j:
                    continue
                jobs.append({
                    "id": f"remoteok|{j.get('id', '')}",
                    "title": j.get("position", ""),
                    "company": j.get("company", "Unknown"),
                    "location": j.get("location", "Remote"),
                    "posted": j.get("date", ""),
                    "url": f"https://remoteok.com/remote-jobs/{j.get('id', '')}",
                    "source": "RemoteOK",
                    "description": " ".join(j.get("tags", []))[:500],
                })
        except Exception as e:
            logger.error(f"RemoteOK error: {e}")
        return jobs


class LinkedInScraper(BaseScraper):
    def scrape(self):
        jobs = []
        for q in LINKEDIN_QUERIES:
            try:
                encoded = urllib.parse.quote(q)
                url = (
                    f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                    f"?keywords={encoded}&location=India&f_TPR=r604800&start=0"
                )
                html = self._get_html(url, timeout=15)
                cards = re.findall(r'<li class=".*?".*?</li>', html, re.DOTALL)
                for card in cards[:25]:
                    title_m = re.search(r'class="base-search-card__title"[^>]*>(.*?)</h3>', card, re.DOTALL)
                    company_m = re.search(r'class="base-search-card__subtitle"[^>]*>.*?>(.*?)</a>', card, re.DOTALL)
                    link_m = re.search(r'href="(https://www\.linkedin\.com/jobs/view/[^"]+)"', card)
                    loc_m = re.search(r'class="job-search-card__location"[^>]*>(.*?)</span>', card, re.DOTALL)
                    title = title_m.group(1).strip() if title_m else ""
                    if not title:
                        continue
                    link = link_m.group(1) if link_m else ""
                    jobs.append({
                        "id": f"linkedin|{link.split('view/')[-1].split('?')[0] if 'view/' in link else title}",
                        "title": title,
                        "company": company_m.group(1).strip() if company_m else "Unknown",
                        "location": loc_m.group(1).strip() if loc_m else "",
                        "posted": "Recent",
                        "url": link,
                        "source": "LinkedIn",
                        "description": "",
                    })
                time.sleep(1)
            except Exception as e:
                logger.error(f"LinkedIn error: {e}")
        return jobs


class UnstopScraper(BaseScraper):
    def scrape(self):
        jobs = []
        try:
            data = self._get_json(
                "https://unstop.com/api/public/opportunity/search-result?opportunity_status=O&type=job&limit=100&offset=0",
                timeout=20,
            )
            for j in data.get("data", {}).get("data", []):
                detail = j.get("detail") or {}
                org = ((j.get("organisation") or {}).get("name", "")) or "Unknown"
                locs = ", ".join(l.get("name", "") for l in (detail.get("location") or []) if l.get("name"))
                jobs.append({
                    "id": f"unstop|{j.get('id', '')}",
                    "title": detail.get("title", ""),
                    "company": org,
                    "location": locs or "India",
                    "posted": (detail.get("start_date", "") or "")[:10] or "N/A",
                    "url": f"https://unstop.com/{detail.get('seo_url', '')}" if detail.get("seo_url") else "https://unstop.com/opportunities",
                    "source": "Unstop",
                    "description": (detail.get("short_description", "") or "")[:2000],
                })
        except Exception as e:
            logger.error(f"Unstop error: {e}")
        return jobs


class InternshalaScraper(BaseScraper):
    """Best-effort HTML scrape of Internshala's GET keyword search."""

    def scrape(self):
        jobs = []
        try:
            html = self._get_html("https://internshala.com/jobs/keywords-graduate-engineer-trainee/", timeout=20)
            cards = re.findall(r'<div class="individual_internship.*?(?=<div class="individual_internship|<div class="view_more_container)', html, re.DOTALL)
            for card in cards[:40]:
                title_m = re.search(r'class="job-title-href"[^>]*>\s*(.*?)\s*</a>', card, re.DOTALL)
                link_m = re.search(r'href="(https://internshala\.com/job/[^"]+)"', card)
                company_m = re.search(r'class="company-name">\s*(.*?)\s*</p>', card, re.DOTALL)
                loc_m = re.search(r'class="locations"[^>]*>.*?<a[^>]*>\s*(.*?)\s*</a>', card, re.DOTALL)
                title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
                if not title:
                    continue
                jobs.append({
                    "id": f"internshala|{(link_m.group(1) if link_m else title)}",
                    "title": title,
                    "company": re.sub(r"<[^>]+>", "", company_m.group(1)).strip() if company_m else "Unknown",
                    "location": re.sub(r"<[^>]+>", "", loc_m.group(1)).strip() if loc_m else "India",
                    "posted": "Recent",
                    "url": link_m.group(1) if link_m else "https://internshala.com/jobs/keywords-graduate-engineer-trainee/",
                    "source": "Internshala",
                    "description": "",
                })
        except Exception as e:
            logger.error(f"Internshala error: {e}")
        return jobs


class PortalAlertScraper(BaseScraper):
    """Surfaces career-page links for volatile portals (PSU, mass recruiters,
    India job boards) so users can check listings/registration windows."""

    def __init__(self, sites, source_label):
        super().__init__()
        self.sites = sites
        self.source_label = source_label

    def scrape(self):
        return [{
            "id": f"{self.source_label.lower()}|{s['name']}",
            "title": f"{s['label']} — careers/registration page",
            "company": s["name"],
            "location": "India",
            "posted": "Check page",
            "url": s["url"],
            "source": self.source_label,
            "description": "Open this portal to view current GET/trainee openings and register.",
        } for s in self.sites]


INDIA_LOCATIONS = []


class GETJobEngine:
    def __init__(self, config, env):
        self.config = config
        self.india_locations = [loc.lower() for loc in config.get("india_locations", INDIA_LOCATIONS)]

        self.workday = WorkdayScraper(config.get("workday_sites", []))
        self.greenhouse = GreenhouseScraper(config.get("greenhouse_companies", []))
        self.lever = LeverScraper(config.get("lever_companies", []))
        self.smartrec = SmartRecruitersScraper(config.get("smartrecruiters_companies", []))
        self.ashby = AshbyScraper(config.get("ashby_companies", []))
        self.adzuna = AdzunaScraper(env.get("ADZUNA_APP_ID", ""), env.get("ADZUNA_APP_KEY", ""))
        self.jooble = JoobleScraper(env.get("JOOBLE_API_KEY", ""))
        self.remotive = RemotiveScraper()
        self.arbeitnow = ArbeitnowScraper()
        self.remoteok = RemoteOKScraper()
        self.linkedin = LinkedInScraper()
        self.unstop = UnstopScraper()
        self.internshala = InternshalaScraper()
        self.portals = PortalAlertScraper(config.get("india_portals", []) + config.get("psu_sites", []), "Portal")
        self.massrec = PortalAlertScraper(config.get("mass_recruiters", []), "MassRecruiter")

        self.last_run = None
        self.last_stats = {}
        self.last_all_jobs = []

    def is_india_job(self, job):
        loc = (job.get("location", "") or "").lower()
        return any(ind in loc for ind in self.india_locations)

    def filter_jobs(self, jobs):
        seen, result = set(), []
        for job in jobs:
            if job["id"] in seen:
                continue
            seen.add(job["id"])
            tag = classify_job(job)
            if tag is None:
                continue
            if not self.is_india_job(job):
                continue
            job["tag"] = tag
            result.append(job)
        return result

    def format_job(self, job):
        msg = (
            f"<b>{job.get('tag', 'GET')} [{job.get('source', '?')}]</b>\n"
            f"<b>{job.get('company', 'Unknown')}: {job['title']}</b>\n"
            f"📍 {job.get('location', 'N/A')}\n"
            f"📅 Posted: {job.get('posted', 'N/A')}\n"
        )
        desc = job.get("description", "")
        if desc:
            msg += f"\n{desc[:150]}...\n"
        msg += f"\n🔗 <a href=\"{job.get('url', '')}\">Apply here</a>"
        return msg

    def generate_csv(self, filepath="get_jobs_export.csv"):
        import csv
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Source", "GET Tag", "Company", "Title", "Location", "Posted", "URL"])
            for job in self.last_all_jobs:
                writer.writerow([
                    job.get("source", ""),
                    job.get("tag", ""),
                    job.get("company", ""),
                    job.get("title", ""),
                    job.get("location", ""),
                    job.get("posted", ""),
                    job.get("url", ""),
                ])
        return filepath

    def get_sources_status(self):
        return {
            "Workday": f"{len(self.workday.sites)} companies",
            "Greenhouse": f"{len(self.greenhouse.companies)} startups",
            "Lever": f"{len(self.lever.companies)} startups",
            "SmartRecruiters": f"{len(self.smartrec.companies)} companies",
            "Ashby": f"{len(self.ashby.companies)} companies",
            "Adzuna": "Active" if self.adzuna.available else "No API key",
            "Jooble": "Active" if self.jooble.available else "No API key",
            "Remotive": "Active",
            "Arbeitnow": "Active",
            "RemoteOK": "Active",
            "LinkedIn": "Active (public)",
            "Unstop": "Active",
            "Internshala": "Active (HTML)",
            "Portals (India+PSU)": f"{len(self.portals.sites)} pages",
            "MassRecruiter": f"{len(self.massrec.sites)} off-campus portals",
        }

    def run_scan(self, sent_ids=None, progress_callback=None):
        if sent_ids is None:
            sent_ids = set()

        all_jobs, stats = [], {}

        scanners = [
            ("Workday", lambda: self._scrape_workday()),
            ("Greenhouse", self.greenhouse.scrape),
            ("Lever", self.lever.scrape),
            ("SmartRecruiters", self.smartrec.scrape),
            ("Ashby", self.ashby.scrape),
            ("Adzuna", self.adzuna.scrape),
            ("Jooble", self.jooble.scrape),
            ("Remotive", self.remotive.scrape),
            ("Arbeitnow", self.arbeitnow.scrape),
            ("RemoteOK", self.remoteok.scrape),
            ("LinkedIn", self.linkedin.scrape),
            ("Unstop", self.unstop.scrape),
            ("Internshala", self.internshala.scrape),
            ("Portals", self.portals.scrape),
            ("MassRecruiter", self.massrec.scrape),
        ]

        for name, fn in scanners:
            try:
                jobs = fn()
                all_jobs.extend(jobs)
                stats[name] = {"total": len(jobs)}
            except Exception as e:
                stats[name] = {"error": str(e)}
            if progress_callback:
                progress_callback(name, stats[name])

        filtered = self.filter_jobs(all_jobs)
        new_jobs = [j for j in filtered if j["id"] not in sent_ids]

        self.last_run = datetime.now().isoformat()
        self.last_all_jobs = all_jobs
        self.last_stats = {
            "total_fetched": len(all_jobs),
            "matching": len(filtered),
            "new_jobs": len(new_jobs),
            "sources": stats,
        }
        return new_jobs

    def _scrape_workday(self):
        jobs = []
        for site in self.workday.sites:
            jobs.extend(self.workday.scrape_site(site))
        return jobs
