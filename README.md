# Job Radar (multi-profile)

Your own job search assistant, built on [Job Radar by akhileshr1122-ui](https://github.com/akhileshr1122-ui/Job-radar-app). It finds jobs that fit your resume across Canada and the US, scores each one, writes a tailored resume and cover letter for the best matches, and lets you review, edit and apply. A web app, an Android app and a Chrome extension all work from the same private GitHub repo.

## What this version adds

- **Several profiles.** Each profile is its own search: its own resume, job titles, locations, tracker and tailored resumes (for example *Data Analyst* and *Product Manager*). Switch between them from the top bar in the web app or from the Jobs screen on Android. All profiles search on the same 4-hour schedule.
- **No company overlap.** One switch (Profiles page) keeps every company in a single profile, so you never apply to the same company under two different personas. A company belongs to the profile you applied from most recently, else the one where you saved one of its jobs, else the one it matches best, and it stays there between searches. Hidden jobs are counted at the top of the list and you can peek at them.
- **Applied before.** Every job shows *Applied before: &lt;title&gt;* when you've applied to that company before, from any profile, and the job page lists each earlier title, profile, date and outcome. Company names are matched loosely (`Shopify Inc.` = `Shopify`, `Wealthsimple Technologies` = `Wealthsimple`, `Faire` = `Faire Wholesale`).
- **Application history.** One list of every application across profiles. Marking a job Applied adds it automatically; you can also add applications you sent before using Job Radar, one at a time or pasted from a spreadsheet (`Company, Title, Date`), so they count too. Filter **New companies only** hides jobs at companies you've already applied to.
- The Chrome extension finds the job in whichever profile has it and fills the form with that profile's resume.

## Set it up (about 15 minutes, free)

You need two repos: a **public** one that hosts the web app and builds the Android app (this code, no personal data), and a **private** one that holds your resumes and results (the web app creates it for you).

1. **Public app repo.** Create a new public repo on GitHub, e.g. `job-radar-app`, and push this folder to it:
   ```
   git init && git add -A && git commit -m "Job Radar multi-profile"
   git branch -M main
   git remote add origin https://github.com/<you>/job-radar-app.git
   git push -u origin main
   ```
2. In that repo's **Settings → General**, tick **Template repository**. In **Settings → Pages**, set *Source* to **GitHub Actions**.
3. In **Actions**, run **Web app** (and **Build apps** for the Android APK and Chrome extension). The web app is then at `https://<you>.github.io/job-radar-app/`; the APK and extension zip are under **Releases**.
4. Open the web app and choose **I'm new**. Make a GitHub token with the `repo` and `workflow` boxes ticked and paste it. This creates your private `job-radar` repo from your template; your resume and results stay there.
5. Upload your resume. That's your first profile. Then open **Profiles** to rename it, add more profiles (with a new resume or the same resume and different job titles), and turn on **No company overlap**.
6. Open **History** and paste the applications you sent before, so they show as *Applied before*.
7. On your phone: install the APK from Releases (Android), or open the web app and *Add to Home Screen* (iPhone or Android). In the Android app, enter your GitHub account, `job-radar` and your token under Settings.

**Already using the original Job Radar?** Your existing private repo works as-is: its data becomes the first profile. Point the web app at it with *I already have a Job Radar repo*, then in its Settings click **Update Job Radar** once, which copies this version's engine and search schedule from your public app repo.

## Where things live (in your private repo)

| Path | What |
|---|---|
| `profile/`, `data/`, `user/` | your first profile ("main"): resume, search settings, results, tracker |
| `profiles/<id>/...` | every other profile, same folders |
| `profiles.json` | the profile list and the no-overlap switch |
| `applications.json` | your application history across all profiles (written by the apps) |
| `shared/` | built by each search: which profile owns each company, and everything you've applied to |

Each search runs the profiles one after another (`engine/multi.py`), then a cross-profile pass (`engine/profiles.py`) stamps every job with its company owner and earlier applications. Each profile searches on its own, so every extra profile adds a few minutes per run and uses its own share of the free job-source keys (JSearch's free plan, for example, allows about 200 searches a month in total).

## Optional upgrades (secrets in your copy: Settings → Secrets and variables → Actions)
| Secret | What it adds |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | AI-written resumes, cover letters and interview prep using **your own Claude Pro or Max plan**. Step-by-step for Windows, Mac and Linux (with fixes for "claude is not recognized") is in the web app under **Settings → AI resumes**. |
| `ANTHROPIC_API_KEY` | Same, billed per use to a Claude API account instead. |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna aggregator (free at developer.adzuna.com). |
| `RAPIDAPI_KEY` | LinkedIn, Indeed, Glassdoor and ZipRecruiter listings via Google for Jobs (JSearch free plan on rapidapi.com). |
| `JOOBLE_KEY` | Jooble aggregator (free). |

Without any of these it still works: free job sources and keyword-based tailoring.

## How applying works
Job Radar never signs in to job sites or submits applications for you. **Apply now** downloads your tailored resume, copies the cover letter and opens the application; the Chrome extension then fills the form (Greenhouse, Lever, Ashby, Workday, Workable, SmartRecruiters and more) and you check it and press Submit.

## What's inside

`engine/` search, scoring, tailoring, profiles (Python, GitHub Actions) · `web/` web app · `app/` Android app · `extension/` Chrome extension · `profile/` your first profile's resume data and search settings.

The hosted Azure mode from the original project is still in the code but supports a single profile only.
