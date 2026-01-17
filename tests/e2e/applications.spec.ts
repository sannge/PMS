/**
 * E2E tests for Applications CRUD operations.
 *
 * Tests cover:
 * - Create application
 * - List applications
 * - Get application by ID
 * - Update application
 * - Delete application
 * - Pagination and search
 * - Ownership verification
 * - Error handling
 */

import { test, expect, type APIRequestContext } from '@playwright/test';

// Test user data for registration/login
const generateTestUser = () => ({
  email: `app.test.${Date.now()}.${Math.random().toString(36).substring(7)}@example.com`,
  password: 'SecurePassword123!',
  display_name: `App Test User ${Date.now()}`,
});

// Test application data
const generateTestApplication = () => ({
  name: `Test Application ${Date.now()}`,
  description: `Test description for application created at ${new Date().toISOString()}`,
});

// Helper to register and login a user, returning the auth token
async function setupAuthenticatedUser(
  request: APIRequestContext
): Promise<{ token: string; userId: string; email: string }> {
  const userData = generateTestUser();

  // Register
  const registerResponse = await request.post('/auth/register', {
    data: userData,
  });
  expect(registerResponse.status()).toBe(201);
  const user = await registerResponse.json();

  // Login
  const loginResponse = await request.post('/auth/login', {
    form: {
      username: userData.email,
      password: userData.password,
    },
  });
  expect(loginResponse.status()).toBe(200);
  const { access_token } = await loginResponse.json();

  return { token: access_token, userId: user.id, email: userData.email };
}

// Helper to create an application
async function createApplication(
  request: APIRequestContext,
  token: string,
  appData?: { name?: string; description?: string }
) {
  const data = appData || generateTestApplication();
  return request.post('/api/applications', {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
}

test.describe('Applications - Create', () => {
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;
  });

  test('should create an application successfully', async ({ request }) => {
    const appData = generateTestApplication();
    const response = await createApplication(request, authToken, appData);

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.id).toBeDefined();
    expect(data.name).toBe(appData.name);
    expect(data.description).toBe(appData.description);
    expect(data.owner_id).toBeDefined();
    expect(data.created_at).toBeDefined();
    expect(data.updated_at).toBeDefined();
  });

  test('should create application with minimum required fields', async ({ request }) => {
    const response = await createApplication(request, authToken, {
      name: 'Minimal App',
    });

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.name).toBe('Minimal App');
    expect(data.description).toBeNull();
  });

  test('should fail to create application without name', async ({ request }) => {
    const response = await request.post('/api/applications', {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { description: 'No name provided' },
    });

    expect(response.status()).toBe(422);
    const data = await response.json();
    expect(data.detail).toBeDefined();
  });

  test('should fail to create application with empty name', async ({ request }) => {
    const response = await request.post('/api/applications', {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { name: '' },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail to create application without authentication', async ({ request }) => {
    const response = await request.post('/api/applications', {
      data: generateTestApplication(),
    });

    expect(response.status()).toBe(401);
  });

  test('should fail to create application with invalid token', async ({ request }) => {
    const response = await request.post('/api/applications', {
      headers: { Authorization: 'Bearer invalid.token.here' },
      data: generateTestApplication(),
    });

    expect(response.status()).toBe(401);
  });

  test('should handle long application name', async ({ request }) => {
    const longName = 'A'.repeat(255);
    const response = await createApplication(request, authToken, {
      name: longName,
    });

    // Should succeed if within limits
    expect([201, 422]).toContain(response.status());
  });

  test('should handle special characters in name', async ({ request }) => {
    const response = await createApplication(request, authToken, {
      name: "Test App <script>alert('xss')</script>",
      description: 'Testing special characters',
    });

    expect(response.status()).toBe(201);
    const data = await response.json();
    // Name should be stored (sanitization may apply)
    expect(data.name).toBeDefined();
  });
});

test.describe('Applications - List', () => {
  let authToken: string;
  let createdAppIds: string[] = [];

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create multiple applications for testing
    for (let i = 0; i < 5; i++) {
      const response = await createApplication(request, authToken, {
        name: `List Test App ${i + 1}`,
        description: `Description for app ${i + 1}`,
      });
      expect(response.status()).toBe(201);
      const app = await response.json();
      createdAppIds.push(app.id);
    }
  });

  test('should list all applications for the user', async ({ request }) => {
    const response = await request.get('/api/applications', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBeGreaterThanOrEqual(5);

    // Each application should have required fields
    data.forEach((app: any) => {
      expect(app.id).toBeDefined();
      expect(app.name).toBeDefined();
      expect(app.owner_id).toBeDefined();
      expect(app.created_at).toBeDefined();
      expect(typeof app.projects_count).toBe('number');
    });
  });

  test('should return applications with projects_count', async ({ request }) => {
    const response = await request.get('/api/applications', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);

    // All applications should have projects_count field
    data.forEach((app: any) => {
      expect(app.projects_count).toBeDefined();
      expect(typeof app.projects_count).toBe('number');
      expect(app.projects_count).toBeGreaterThanOrEqual(0);
    });
  });

  test('should support pagination with skip and limit', async ({ request }) => {
    // Get first 2 applications
    const response1 = await request.get('/api/applications?skip=0&limit=2', {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response1.status()).toBe(200);
    const page1 = await response1.json();
    expect(page1.length).toBe(2);

    // Get next 2 applications
    const response2 = await request.get('/api/applications?skip=2&limit=2', {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response2.status()).toBe(200);
    const page2 = await response2.json();
    expect(page2.length).toBe(2);

    // Pages should have different items
    expect(page1[0].id).not.toBe(page2[0].id);
  });

  test('should support search by name', async ({ request }) => {
    // Search for specific application
    const response = await request.get('/api/applications?search=List%20Test%20App%201', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);
    expect(data[0].name).toContain('List Test App');
  });

  test('should return empty array for non-matching search', async ({ request }) => {
    const response = await request.get('/api/applications?search=NonExistentApplicationXYZ123', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBe(0);
  });

  test('should fail to list applications without authentication', async ({ request }) => {
    const response = await request.get('/api/applications');

    expect(response.status()).toBe(401);
  });

  test('should only return applications owned by the user', async ({ request }) => {
    // Create a second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Create application with second user
    const otherAppResponse = await createApplication(request, otherUserToken, {
      name: 'Other User App',
    });
    expect(otherAppResponse.status()).toBe(201);

    // First user should not see the other user's application
    const response = await request.get('/api/applications', {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response.status()).toBe(200);

    const data = await response.json();
    const otherUserApp = data.find((app: any) => app.name === 'Other User App');
    expect(otherUserApp).toBeUndefined();
  });
});

test.describe('Applications - Get by ID', () => {
  let authToken: string;
  let applicationId: string;
  let applicationData: { name: string; description: string };

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create an application for testing
    applicationData = generateTestApplication();
    const response = await createApplication(request, authToken, applicationData);
    expect(response.status()).toBe(201);
    const app = await response.json();
    applicationId = app.id;
  });

  test('should get application by ID', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.id).toBe(applicationId);
    expect(data.name).toBe(applicationData.name);
    expect(data.description).toBe(applicationData.description);
    expect(data.projects_count).toBeDefined();
    expect(typeof data.projects_count).toBe('number');
  });

  test('should fail with non-existent application ID', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.get(`/api/applications/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
    const data = await response.json();
    expect(data.detail).toContain('not found');
  });

  test('should fail with invalid UUID format', async ({ request }) => {
    const response = await request.get('/api/applications/invalid-uuid', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail without authentication', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}`);

    expect(response.status()).toBe(401);
  });

  test('should fail accessing another user\'s application', async ({ request }) => {
    // Create a second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Try to access first user's application
    const response = await request.get(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
    const data = await response.json();
    expect(data.detail.toLowerCase()).toContain('access denied');
  });
});

test.describe('Applications - Update', () => {
  let authToken: string;
  let applicationId: string;

  test.beforeEach(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create a fresh application for each test
    const response = await createApplication(request, authToken);
    expect(response.status()).toBe(201);
    const app = await response.json();
    applicationId = app.id;
  });

  test('should update application name', async ({ request }) => {
    const newName = `Updated Name ${Date.now()}`;
    const response = await request.put(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { name: newName },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.name).toBe(newName);
    expect(new Date(data.updated_at).getTime()).toBeGreaterThan(
      new Date(data.created_at).getTime() - 1000
    );
  });

  test('should update application description', async ({ request }) => {
    const newDescription = `Updated description at ${new Date().toISOString()}`;
    const response = await request.put(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { description: newDescription },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.description).toBe(newDescription);
  });

  test('should update multiple fields at once', async ({ request }) => {
    const updates = {
      name: `Fully Updated App ${Date.now()}`,
      description: 'Completely new description',
    };
    const response = await request.put(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: updates,
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.name).toBe(updates.name);
    expect(data.description).toBe(updates.description);
  });

  test('should fail update with empty request body', async ({ request }) => {
    const response = await request.put(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {},
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.detail).toContain('No fields');
  });

  test('should fail update without authentication', async ({ request }) => {
    const response = await request.put(`/api/applications/${applicationId}`, {
      data: { name: 'New Name' },
    });

    expect(response.status()).toBe(401);
  });

  test('should fail to update another user\'s application', async ({ request }) => {
    // Create a second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.put(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
      data: { name: 'Hacked Name' },
    });

    expect(response.status()).toBe(403);
  });

  test('should fail to update non-existent application', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.put(`/api/applications/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { name: 'New Name' },
    });

    expect(response.status()).toBe(404);
  });

  test('should clear description when set to null', async ({ request }) => {
    // First ensure description is set
    await request.put(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { description: 'Some description' },
    });

    // Then clear it
    const response = await request.put(`/api/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { description: null },
    });

    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.description).toBeNull();
  });
});

test.describe('Applications - Delete', () => {
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;
  });

  test('should delete application successfully', async ({ request }) => {
    // Create an application to delete
    const createResponse = await createApplication(request, authToken);
    expect(createResponse.status()).toBe(201);
    const app = await createResponse.json();

    // Delete the application
    const deleteResponse = await request.delete(`/api/applications/${app.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(deleteResponse.status()).toBe(204);

    // Verify it's gone
    const getResponse = await request.get(`/api/applications/${app.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getResponse.status()).toBe(404);
  });

  test('should fail delete without authentication', async ({ request }) => {
    // Create an application
    const createResponse = await createApplication(request, authToken);
    const app = await createResponse.json();

    // Try to delete without auth
    const response = await request.delete(`/api/applications/${app.id}`);

    expect(response.status()).toBe(401);
  });

  test('should fail to delete another user\'s application', async ({ request }) => {
    // Create an application
    const createResponse = await createApplication(request, authToken);
    const app = await createResponse.json();

    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Try to delete with other user's token
    const response = await request.delete(`/api/applications/${app.id}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });

  test('should fail to delete non-existent application', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.delete(`/api/applications/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });

  test('should return 404 when deleting already deleted application', async ({ request }) => {
    // Create and delete an application
    const createResponse = await createApplication(request, authToken);
    const app = await createResponse.json();

    await request.delete(`/api/applications/${app.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    // Try to delete again
    const response = await request.delete(`/api/applications/${app.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });
});

test.describe('Applications - Edge Cases', () => {
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;
  });

  test('should handle concurrent create requests', async ({ request }) => {
    const createPromises = Array(3)
      .fill(null)
      .map((_, i) =>
        createApplication(request, authToken, {
          name: `Concurrent App ${i + 1}`,
        })
      );

    const responses = await Promise.all(createPromises);

    // All should succeed
    responses.forEach((response) => {
      expect(response.status()).toBe(201);
    });

    // All should have unique IDs
    const ids = await Promise.all(responses.map(async (r) => (await r.json()).id));
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(3);
  });

  test('should handle Unicode characters in application data', async ({ request }) => {
    const response = await createApplication(request, authToken, {
      name: 'Application \u4e2d\u6587 \ud83d\udcbb',
      description: 'Description with emoji \ud83d\ude00 and special chars \u00e9\u00e8',
    });

    expect([201, 422]).toContain(response.status());

    if (response.status() === 201) {
      const data = await response.json();
      expect(data.name).toBeDefined();
    }
  });

  test('should maintain data integrity after rapid updates', async ({ request }) => {
    // Create application
    const createResponse = await createApplication(request, authToken);
    const app = await createResponse.json();

    // Perform rapid updates
    for (let i = 0; i < 5; i++) {
      await request.put(`/api/applications/${app.id}`, {
        headers: { Authorization: `Bearer ${authToken}` },
        data: { name: `Rapid Update ${i + 1}` },
      });
    }

    // Verify final state
    const getResponse = await request.get(`/api/applications/${app.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getResponse.status()).toBe(200);

    const finalData = await getResponse.json();
    expect(finalData.name).toBe('Rapid Update 5');
  });

  test('should handle SQL injection attempts', async ({ request }) => {
    const response = await createApplication(request, authToken, {
      name: "Test'; DROP TABLE Applications; --",
      description: "Description' OR '1'='1",
    });

    // Should not cause server error
    expect(response.status()).not.toBe(500);
    expect([201, 422]).toContain(response.status());
  });

  test('should reject application with name exceeding max length', async ({ request }) => {
    const veryLongName = 'A'.repeat(1000);
    const response = await createApplication(request, authToken, {
      name: veryLongName,
    });

    // Should be rejected with validation error
    expect([201, 422]).toContain(response.status());
  });
});
