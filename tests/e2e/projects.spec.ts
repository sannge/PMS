/**
 * E2E tests for Projects CRUD operations.
 *
 * Tests cover:
 * - Create project within application
 * - List projects in application
 * - Get project by ID
 * - Update project
 * - Delete project
 * - Pagination and filtering
 * - Application ownership verification
 * - Error handling
 */

import { test, expect, type APIRequestContext } from '@playwright/test';

// Test user data for registration/login
const generateTestUser = () => ({
  email: `proj.test.${Date.now()}.${Math.random().toString(36).substring(7)}@example.com`,
  password: 'SecurePassword123!',
  display_name: `Project Test User ${Date.now()}`,
});

// Test application data
const generateTestApplication = () => ({
  name: `Test App for Projects ${Date.now()}`,
  description: 'Test application for project tests',
});

// Test project data
const generateTestProject = () => ({
  name: `Test Project ${Date.now()}`,
  key: `PRJ${Date.now().toString().slice(-4)}`.toUpperCase(),
  description: `Test description for project created at ${new Date().toISOString()}`,
  project_type: 'kanban',
});

// Helper to register and login a user, returning the auth token
async function setupAuthenticatedUser(
  request: APIRequestContext
): Promise<{ token: string; userId: string }> {
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

  return { token: access_token, userId: user.id };
}

// Helper to create an application
async function createApplication(
  request: APIRequestContext,
  token: string,
  appData?: { name?: string; description?: string }
): Promise<{ id: string; name: string }> {
  const data = appData || generateTestApplication();
  const response = await request.post('/api/applications', {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(response.status()).toBe(201);
  return response.json();
}

// Helper to create a project
async function createProject(
  request: APIRequestContext,
  token: string,
  applicationId: string,
  projectData?: { name?: string; key?: string; description?: string; project_type?: string }
) {
  const data = projectData || generateTestProject();
  return request.post(`/api/applications/${applicationId}/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
}

test.describe('Projects - Create', () => {
  let authToken: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create an application to hold projects
    const app = await createApplication(request, authToken);
    applicationId = app.id;
  });

  test('should create a project successfully', async ({ request }) => {
    const projectData = generateTestProject();
    const response = await createProject(request, authToken, applicationId, projectData);

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.id).toBeDefined();
    expect(data.name).toBe(projectData.name);
    expect(data.key).toBe(projectData.key);
    expect(data.description).toBe(projectData.description);
    expect(data.project_type).toBe(projectData.project_type);
    expect(data.application_id).toBe(applicationId);
    expect(data.created_at).toBeDefined();
    expect(data.updated_at).toBeDefined();
  });

  test('should create project with scrum type', async ({ request }) => {
    const response = await createProject(request, authToken, applicationId, {
      name: 'Scrum Project',
      key: `SCR${Date.now().toString().slice(-4)}`,
      project_type: 'scrum',
    });

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.project_type).toBe('scrum');
  });

  test('should create project with minimum required fields', async ({ request }) => {
    const response = await createProject(request, authToken, applicationId, {
      name: 'Minimal Project',
      key: `MIN${Date.now().toString().slice(-4)}`,
    });

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.name).toBe('Minimal Project');
    expect(data.description).toBeNull();
    // Default project_type should be set
    expect(data.project_type).toBeDefined();
  });

  test('should fail to create project without name', async ({ request }) => {
    const response = await request.post(`/api/applications/${applicationId}/projects`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {
        key: 'NONAME',
        description: 'Missing name',
      },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail to create project without key', async ({ request }) => {
    const response = await request.post(`/api/applications/${applicationId}/projects`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {
        name: 'No Key Project',
        description: 'Missing key',
      },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail to create project with duplicate key in same application', async ({ request }) => {
    const projectKey = `DUP${Date.now().toString().slice(-4)}`;

    // Create first project
    const firstResponse = await createProject(request, authToken, applicationId, {
      name: 'First Project',
      key: projectKey,
    });
    expect(firstResponse.status()).toBe(201);

    // Try to create second project with same key
    const secondResponse = await createProject(request, authToken, applicationId, {
      name: 'Second Project',
      key: projectKey,
    });

    expect(secondResponse.status()).toBe(400);
    const data = await secondResponse.json();
    expect(data.detail.toLowerCase()).toContain('already exists');
  });

  test('should allow same key in different applications', async ({ request }) => {
    // Create another application
    const otherApp = await createApplication(request, authToken, {
      name: 'Other App for Projects',
    });

    const sharedKey = `SHR${Date.now().toString().slice(-4)}`;

    // Create project in first application
    const first = await createProject(request, authToken, applicationId, {
      name: 'Project in App 1',
      key: sharedKey,
    });
    expect(first.status()).toBe(201);

    // Create project with same key in different application
    const second = await createProject(request, authToken, otherApp.id, {
      name: 'Project in App 2',
      key: sharedKey,
    });
    expect(second.status()).toBe(201);
  });

  test('should fail to create project without authentication', async ({ request }) => {
    const response = await request.post(`/api/applications/${applicationId}/projects`, {
      data: generateTestProject(),
    });

    expect(response.status()).toBe(401);
  });

  test('should fail to create project in non-existent application', async ({ request }) => {
    const fakeAppId = '00000000-0000-0000-0000-000000000000';
    const response = await createProject(request, authToken, fakeAppId, generateTestProject());

    expect(response.status()).toBe(404);
  });

  test('should fail to create project in another user\'s application', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Try to create project in first user's application
    const response = await createProject(request, otherUserToken, applicationId, generateTestProject());

    expect(response.status()).toBe(403);
  });
});

test.describe('Projects - List', () => {
  let authToken: string;
  let applicationId: string;
  let createdProjectIds: string[] = [];

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create an application
    const app = await createApplication(request, authToken);
    applicationId = app.id;

    // Create multiple projects for testing
    for (let i = 0; i < 5; i++) {
      const response = await createProject(request, authToken, applicationId, {
        name: `List Test Project ${i + 1}`,
        key: `LTP${i}${Date.now().toString().slice(-3)}`,
        project_type: i % 2 === 0 ? 'kanban' : 'scrum',
      });
      expect(response.status()).toBe(201);
      const project = await response.json();
      createdProjectIds.push(project.id);
    }
  });

  test('should list all projects in an application', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/projects`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBeGreaterThanOrEqual(5);

    // Each project should have required fields
    data.forEach((project: any) => {
      expect(project.id).toBeDefined();
      expect(project.name).toBeDefined();
      expect(project.key).toBeDefined();
      expect(project.application_id).toBe(applicationId);
      expect(typeof project.tasks_count).toBe('number');
    });
  });

  test('should return projects with tasks_count', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/projects`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    data.forEach((project: any) => {
      expect(project.tasks_count).toBeDefined();
      expect(typeof project.tasks_count).toBe('number');
      expect(project.tasks_count).toBeGreaterThanOrEqual(0);
    });
  });

  test('should support pagination with skip and limit', async ({ request }) => {
    // Get first 2 projects
    const response1 = await request.get(`/api/applications/${applicationId}/projects?skip=0&limit=2`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response1.status()).toBe(200);
    const page1 = await response1.json();
    expect(page1.length).toBe(2);

    // Get next 2 projects
    const response2 = await request.get(`/api/applications/${applicationId}/projects?skip=2&limit=2`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response2.status()).toBe(200);
    const page2 = await response2.json();
    expect(page2.length).toBe(2);

    // Pages should have different items
    expect(page1[0].id).not.toBe(page2[0].id);
  });

  test('should support search by name', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/projects?search=List%20Test%20Project%201`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);
    expect(data[0].name).toContain('List Test Project');
  });

  test('should support filter by project_type', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/projects?project_type=kanban`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);
    data.forEach((project: any) => {
      expect(project.project_type).toBe('kanban');
    });
  });

  test('should return empty array for non-existent application', async ({ request }) => {
    const fakeAppId = '00000000-0000-0000-0000-000000000000';
    const response = await request.get(`/api/applications/${fakeAppId}/projects`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });

  test('should fail to list projects without authentication', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/projects`);

    expect(response.status()).toBe(401);
  });

  test('should not list projects from another user\'s application', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.get(`/api/applications/${applicationId}/projects`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });
});

test.describe('Projects - Get by ID', () => {
  let authToken: string;
  let applicationId: string;
  let projectId: string;
  let projectData: { name: string; key: string; description: string };

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create an application
    const app = await createApplication(request, authToken);
    applicationId = app.id;

    // Create a project
    projectData = {
      name: 'Get By ID Test Project',
      key: `GID${Date.now().toString().slice(-4)}`,
      description: 'Project for get by ID tests',
    };
    const response = await createProject(request, authToken, applicationId, projectData);
    expect(response.status()).toBe(201);
    const project = await response.json();
    projectId = project.id;
  });

  test('should get project by ID', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.id).toBe(projectId);
    expect(data.name).toBe(projectData.name);
    expect(data.key).toBe(projectData.key);
    expect(data.description).toBe(projectData.description);
    expect(data.application_id).toBe(applicationId);
    expect(data.tasks_count).toBeDefined();
  });

  test('should fail with non-existent project ID', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.get(`/api/projects/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
    const data = await response.json();
    expect(data.detail).toContain('not found');
  });

  test('should fail with invalid UUID format', async ({ request }) => {
    const response = await request.get('/api/projects/invalid-uuid', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail without authentication', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}`);

    expect(response.status()).toBe(401);
  });

  test('should fail accessing another user\'s project', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.get(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });
});

test.describe('Projects - Update', () => {
  let authToken: string;
  let applicationId: string;
  let projectId: string;

  test.beforeEach(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create an application
    const app = await createApplication(request, authToken);
    applicationId = app.id;

    // Create a fresh project for each test
    const response = await createProject(request, authToken, applicationId);
    expect(response.status()).toBe(201);
    const project = await response.json();
    projectId = project.id;
  });

  test('should update project name', async ({ request }) => {
    const newName = `Updated Project Name ${Date.now()}`;
    const response = await request.put(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { name: newName },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.name).toBe(newName);
  });

  test('should update project description', async ({ request }) => {
    const newDescription = `Updated description at ${new Date().toISOString()}`;
    const response = await request.put(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { description: newDescription },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.description).toBe(newDescription);
  });

  test('should update project type', async ({ request }) => {
    const response = await request.put(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { project_type: 'scrum' },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.project_type).toBe('scrum');
  });

  test('should update multiple fields at once', async ({ request }) => {
    const updates = {
      name: `Fully Updated Project ${Date.now()}`,
      description: 'Completely new description',
      project_type: 'scrum',
    };
    const response = await request.put(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: updates,
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.name).toBe(updates.name);
    expect(data.description).toBe(updates.description);
    expect(data.project_type).toBe(updates.project_type);
  });

  test('should fail update with empty request body', async ({ request }) => {
    const response = await request.put(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {},
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.detail).toContain('No fields');
  });

  test('should fail update without authentication', async ({ request }) => {
    const response = await request.put(`/api/projects/${projectId}`, {
      data: { name: 'New Name' },
    });

    expect(response.status()).toBe(401);
  });

  test('should fail to update another user\'s project', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.put(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
      data: { name: 'Hacked Name' },
    });

    expect(response.status()).toBe(403);
  });

  test('should fail to update non-existent project', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.put(`/api/projects/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { name: 'New Name' },
    });

    expect(response.status()).toBe(404);
  });

  test('should not allow changing project key', async ({ request }) => {
    // Note: Project key should not be changeable after creation
    // This test verifies the API doesn't allow key changes
    const response = await request.put(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { key: 'NEWKEY' }, // Attempting to change key
    });

    // If key is in update schema, it should be ignored or rejected
    // Check that the key remains unchanged
    if (response.status() === 200) {
      const data = await response.json();
      // Key should remain unchanged
      expect(data.key).not.toBe('NEWKEY');
    }
  });
});

test.describe('Projects - Delete', () => {
  let authToken: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create an application
    const app = await createApplication(request, authToken);
    applicationId = app.id;
  });

  test('should delete project successfully', async ({ request }) => {
    // Create a project to delete
    const createResponse = await createProject(request, authToken, applicationId);
    expect(createResponse.status()).toBe(201);
    const project = await createResponse.json();

    // Delete the project
    const deleteResponse = await request.delete(`/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(deleteResponse.status()).toBe(204);

    // Verify it's gone
    const getResponse = await request.get(`/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getResponse.status()).toBe(404);
  });

  test('should fail delete without authentication', async ({ request }) => {
    // Create a project
    const createResponse = await createProject(request, authToken, applicationId);
    const project = await createResponse.json();

    // Try to delete without auth
    const response = await request.delete(`/api/projects/${project.id}`);

    expect(response.status()).toBe(401);
  });

  test('should fail to delete another user\'s project', async ({ request }) => {
    // Create a project
    const createResponse = await createProject(request, authToken, applicationId);
    const project = await createResponse.json();

    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Try to delete with other user's token
    const response = await request.delete(`/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });

  test('should fail to delete non-existent project', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.delete(`/api/projects/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });

  test('should return 404 when deleting already deleted project', async ({ request }) => {
    // Create and delete a project
    const createResponse = await createProject(request, authToken, applicationId);
    const project = await createResponse.json();

    await request.delete(`/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    // Try to delete again
    const response = await request.delete(`/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });
});

test.describe('Projects - Edge Cases', () => {
  let authToken: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    // Create an application
    const app = await createApplication(request, authToken);
    applicationId = app.id;
  });

  test('should handle concurrent create requests', async ({ request }) => {
    const createPromises = Array(3)
      .fill(null)
      .map((_, i) =>
        createProject(request, authToken, applicationId, {
          name: `Concurrent Project ${i + 1}`,
          key: `CP${i}${Date.now().toString().slice(-3)}`,
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

  test('should handle Unicode characters in project data', async ({ request }) => {
    const response = await createProject(request, authToken, applicationId, {
      name: 'Project \u4e2d\u6587 \ud83d\udcbc',
      key: `UNI${Date.now().toString().slice(-4)}`,
      description: 'Description with emoji \ud83d\ude80 and special chars \u00e9\u00e8',
    });

    expect([201, 422]).toContain(response.status());

    if (response.status() === 201) {
      const data = await response.json();
      expect(data.name).toBeDefined();
    }
  });

  test('should handle SQL injection attempts', async ({ request }) => {
    const response = await createProject(request, authToken, applicationId, {
      name: "Project'; DROP TABLE Projects; --",
      key: `SQL${Date.now().toString().slice(-4)}`,
      description: "Description' OR '1'='1",
    });

    // Should not cause server error
    expect(response.status()).not.toBe(500);
    expect([201, 422]).toContain(response.status());
  });

  test('should maintain project-application relationship after update', async ({ request }) => {
    // Create project
    const createResponse = await createProject(request, authToken, applicationId);
    const project = await createResponse.json();

    // Update project
    await request.put(`/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { name: 'Updated Name' },
    });

    // Verify application_id hasn't changed
    const getResponse = await request.get(`/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const updatedProject = await getResponse.json();
    expect(updatedProject.application_id).toBe(applicationId);
  });

  test('should delete project when parent application is deleted', async ({ request }) => {
    // Create a new application with a project
    const app = await createApplication(request, authToken, {
      name: 'App to be deleted',
    });
    const projectResponse = await createProject(request, authToken, app.id, {
      name: 'Project in deleted app',
      key: `DEL${Date.now().toString().slice(-4)}`,
    });
    const project = await projectResponse.json();

    // Delete the application
    await request.delete(`/api/applications/${app.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    // Project should also be deleted (cascade)
    const getProjectResponse = await request.get(`/api/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getProjectResponse.status()).toBe(404);
  });
});
