// Week-3 browser test (Playwright): search -> record detail journey.
// Run: npx playwright test  (needs API on :8000 + `npm run dev` on :5173)
import { test, expect } from '@playwright/test';
test('search to record detail', async ({ page }) => {
  await page.goto('http://localhost:5173/');
  await page.getByRole('textbox').first().fill('spodumene');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByText(/hits in/)).toBeVisible();
  await page.getByText(/lithium carbonate from spodumene/).click();
  await expect(page.getByTestId('record-detail')).toContainText('PAT-LI-001');
});
