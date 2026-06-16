# OpenWatari documentation site

A [Next.js](https://nextjs.org) (App Router) static documentation site for **OpenWatari**.

## Local development

```bash
cd website
npm install
npm run dev      # http://localhost:3000
npm run build    # production build (what Vercel runs)
```

## Deploy to Vercel

The site lives in the `website/` subdirectory of the repo, so point Vercel at it:

**Option A — dashboard (recommended)**
1. Push the repo to GitHub (it's `iamvazghen/OpenWatari`).
2. In Vercel → **Add New… → Project** → import the repo.
3. Set **Root Directory** = `website`. Framework preset auto-detects **Next.js**.
4. Deploy. You get `https://<project>.vercel.app` (e.g. `https://openwatari.vercel.app`).

**Option B — CLI**
```bash
npm i -g vercel
vercel --cwd website          # first run links/creates the project (set root dir = ./)
vercel --cwd website --prod   # production deploy
```

No environment variables are needed — the site is fully static content.

## Structure

```
website/
  app/
    layout.tsx          # shared shell + sidebar nav
    globals.css         # styling
    page.tsx            # Overview
    quickstart/         # install + setup wizard
    architecture/       # edge/brain split + memory layers
    networking/         # the Tailnet requirement
    devices/            # all 7 device setups (Mentra, HA, laptop±headphones, phone±headphones, PC control)
    configuration/      # env knobs
    security/           # enforced safety model
    license/            # MIT + third-party + naming
```
