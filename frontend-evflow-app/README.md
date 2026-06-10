# EVFlow Frontend

React and React Native TypeScript monorepo for EVFlow. The codebase is structured so business logic, UI primitives, maps, and screens can be shared across web, Android, and iOS.

## Project Structure

```text
apps/
  mobile/       Expo React Native app for Android and iOS
  web/          React web app powered by Vite and React Native Web

packages/
  shared/       API client, TypeScript types, data helpers, charger filtering, route planning logic
  ui/           Shared buttons, cards, filters, and layout components
  maps/         Platform-specific MapView.web.tsx and MapView.native.tsx
  features/     Shared feature modules and screens used by mobile and web apps
```

`packages/features` is the recommended additional directory for screens and user flows. Keep `apps/mobile` and `apps/web` focused on platform startup code, while feature screens live in reusable modules.

## Prerequisites

- Node.js 20 or newer
- npm 10 or newer
- Expo tooling through `npx expo`
- Android Studio for Android emulator builds
- Xcode for iOS simulator builds on macOS

## Install

```bash
npm install
```

## Run Mobile

Start Expo from the mobile app workspace:

```bash
npm run mobile
```

Run on a physical device over the same Wi-Fi network:

```bash
npm run mobile:lan
```

If Expo Go cannot connect to a local `exp://192.168.x.x:8081` URL, use a tunnel instead:

```bash
npm run mobile:tunnel
```

Use tunnel mode when the phone and computer are on different networks, a VPN is active, a firewall blocks port `8081`, or the Wi-Fi network blocks device-to-device traffic.

Run Android:

```bash
npm run mobile:android
```

Run iOS:

```bash
npm run mobile:ios
```

You can also run Expo directly:

```bash
npm run start --workspace @evflow/mobile
```

## Run Web

Start the Vite web app:

```bash
npm run web
```

Build the web app:

```bash
npm run build:web
```

Preview the production web build:

```bash
npm run preview --workspace @evflow/web
```

## Typecheck

```bash
npm run typecheck
```

## Mobile Build And Deployment

This app is ready to use Expo Application Services.

Install and log in to EAS:

```bash
npm install -g eas-cli
eas login
```

Configure native builds:

```bash
cd apps/mobile
eas build:configure
```

Create Android and iOS builds:

```bash
eas build --platform android
eas build --platform ios
```

Submit builds to app stores:

```bash
eas submit --platform android
eas submit --platform ios
```

## Web Deployment

The web output is generated in `apps/web/dist`.

```bash
npm run build:web
```

Deploy `apps/web/dist` to a static host such as Vercel, Netlify, Cloudflare Pages, or GitHub Pages.

## Repository

This app lives in the `evflow-fullstack` monorepo alongside the FastAPI backend (`backend-ev-flow/`). See the repository root README for fullstack setup.
