import { test, expect } from '@playwright/test';
test('all workspace pages, real feedback and import validation', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Customer Experience Overview' })).toBeVisible();
  await expect(page.getByText('Backend connected')).toBeVisible();
  await expect(page.getByText('Total Feedback', { exact: true })).toBeVisible();
  await page.screenshot({
    path: '../.artifacts/screenshots/dashboard-desktop.png',
    fullPage: true,
  });
  const pages = [
    ['Feedback', 'Feedback Explorer'],
    ['Analytics', 'Customer experience analytics'],
    ['Recovery', 'Recovery Cases'],
    ['Recommendations', 'Recommendations'],
    ['Human Review', 'Human Review'],
    ['Settings', 'Workspace Settings'],
  ];
  for (const [nav, title] of pages) {
    await page.getByRole('navigation').getByRole('link', { name: nav, exact: true }).click();
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(page.getByLabel('Loading workspace')).toHaveCount(0);
    await expect(page.getByRole('main').getByRole('alert')).toHaveCount(0);
    await page.screenshot({
      path: `../.artifacts/screenshots/${nav.toLowerCase().replaceAll(' ', '-')}.png`,
      fullPage: true,
    });
  }
  await page.getByRole('navigation').getByRole('link', { name: 'Feedback', exact: true }).click();
  await expect(page.getByLabel('Loading workspace')).toHaveCount(0);
  const records = page.locator('.record-link');
  if (await records.count()) {
    await records.first().click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Classification', exact: true })).toBeVisible();
    await page.screenshot({ path: '../.artifacts/screenshots/feedback-detail.png' });
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }
  await page.getByRole('button', { name: 'Import feedback', exact: true }).click();
  await page
    .getByLabel('Excel workbook')
    .setInputFiles({ name: 'invalid.csv', mimeType: 'text/csv', buffer: Buffer.from('test') });
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('.xlsx');
  await expect(page.getByRole('button', { name: 'Import workbook', exact: true })).toBeDisabled();
  await page.screenshot({ path: '../.artifacts/screenshots/import-validation.png' });
  await page.keyboard.press('Escape');
  expect(errors).toEqual([]);
});
test('tablet layout stays within the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 1100 });
  await page.goto('/');
  await expect(page.getByText('Total Feedback', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: '../.artifacts/screenshots/dashboard-tablet.png', fullPage: true });
  await page.getByRole('navigation').getByRole('link', { name: 'Feedback', exact: true }).click();
  await expect(page.getByLabel('Loading workspace')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: '../.artifacts/screenshots/feedback-tablet.png', fullPage: true });
});
