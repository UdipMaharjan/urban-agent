import { test, expect } from '@playwright/test';
test('manager imports, analyzes, resumes views and confirms re-analysis without Swagger', async ({
  page,
  request,
}) => {
  // Refuse to submit analysis unless the isolated offline fixture is running.
  const identity = await request.get('/backend/__test__/identity');
  expect((await identity.json()).offline_fixture).toBe(true);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/feedback');
  await page.getByRole('button', { name: 'Import feedback', exact: true }).click();
  const workbook = await request.get('/backend/__test__/workbook');
  await page.getByLabel('Excel workbook').setInputFiles({
    name: 'browser-fixture.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: await workbook.body(),
  });
  await page.getByRole('button', { name: 'Import workbook', exact: true }).click();
  await expect(
    page.getByText('2 feedback imported. Analysis starts only after you confirm.'),
  ).toBeVisible();
  expect((await (await request.get('/backend/__test__/identity')).json()).llm_calls).toBe(0);
  await page.getByRole('button', { name: 'Analyze 2 feedback', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveAccessibleName(
    'Analyze 2 pending feedback records?',
  );
  await page.screenshot({ path: '../.artifacts/screenshots/analysis-confirmation.png' });
  await page.getByRole('button', { name: 'Analyze 2 feedback', exact: true }).click();
  await expect(page.getByText('Analysis complete', { exact: true })).toBeVisible();
  expect((await (await request.get('/backend/__test__/identity')).json()).llm_calls).toBe(4);
  await page.screenshot({ path: '../.artifacts/screenshots/analysis-complete.png' });
  await page.getByRole('link', { name: 'Review flagged items (1)' }).click();
  await expect(page.getByRole('button', { name: 'UI-REVIEW', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'UI-REVIEW', exact: true }).click();
  await expect(page.getByText('Review the reported impact.')).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('navigation').getByRole('link', { name: 'Dashboard', exact: true }).click();
  await expect(page.locator('.stat').filter({ hasText: 'Negative Feedback' })).toContainText(
    '100.0%',
  );
  await page.screenshot({
    path: '../.artifacts/screenshots/analysis-dashboard-offline-fixture.png',
    fullPage: true,
  });
  await page.getByRole('navigation').getByRole('link', { name: 'Feedback', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Analyze pending feedback', exact: true }),
  ).toBeDisabled();
  await page.getByRole('button', { name: 'Import feedback', exact: true }).click();
  const single = await request.get('/backend/__test__/workbook?single=true');
  await page.getByLabel('Excel workbook').setInputFiles({
    name: 'single.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: await single.body(),
  });
  await page.getByRole('button', { name: 'Import workbook', exact: true }).click();
  await page.getByRole('button', { name: 'Done', exact: true }).click();
  const row = page
    .getByRole('row')
    .filter({ has: page.getByRole('button', { name: 'UI-SINGLE', exact: true }) });
  await expect(row).toContainText('Pending');
  await page.getByRole('button', { name: 'UI-SINGLE', exact: true }).click();
  await page.getByRole('button', { name: 'Analyze feedback', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm analysis', exact: true }).click();
  await expect(page.getByText('Analysis complete', { exact: true })).toBeVisible();
  await page
    .getByRole('dialog', { name: 'Analysis complete' })
    .getByRole('button', { name: 'Close dialog' })
    .click();
  await expect(page.getByText('Classification is supported by the source feedback.')).toBeVisible();
  await page.getByRole('button', { name: 'Re-analyze', exact: true }).click();
  expect((await (await request.get('/backend/__test__/identity')).json()).llm_calls).toBe(6);
  await page.getByRole('button', { name: 'Confirm re-analysis', exact: true }).click();
  await expect(page.getByText('Analysis complete', { exact: true })).toBeVisible();
  expect((await (await request.get('/backend/__test__/identity')).json()).llm_calls).toBe(8);
  expect(errors).toEqual([]);
});
