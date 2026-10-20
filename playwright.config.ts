import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'tests/e2e', timeout:30000, fullyParallel:false, workers:1,
  use:{baseURL:'http://127.0.0.1:5173',browserName:'chromium',launchOptions:{executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']},trace:'retain-on-failure'},
  reporter:[['list'],['html',{open:'never'}]],
  webServer:[
    {command:'.venv/bin/python -m uvicorn sales_intelligence.api:app --host 127.0.0.1 --port 8000',url:'http://127.0.0.1:8000/api/health',reuseExistingServer:!process.env.CI,env:{APP_PASSWORD:'e2e-fixture-password-not-production',SESSION_SECRET:'e2e-fixture-signing-key-not-production-1234',COOKIE_SECURE:'false',CALLS_ANNOTATIONS_PATH:process.env.CALLS_ANNOTATIONS_PATH || ''}},
    {command:'npm run dev -- --port 5173',url:'http://127.0.0.1:5173',reuseExistingServer:!process.env.CI}
  ]
});
