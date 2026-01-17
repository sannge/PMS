/**
 * E2E tests for Tasks CRUD operations.
 *
 * Tests cover:
 * - Create task within project
 * - List tasks in project
 * - Get task by ID
 * - Update task (including status transitions)
 * - Delete task
 * - Pagination and filtering
 * - Task hierarchy (subtasks)
 * - Auto-generated task keys
 * - Error handling
 */

import { test, expect, type APIRequestContext } from '@playwright/test';

// Test user data for registration/login
const generateTestUser = () => ({
  email: `task.test.${Date.now()}.${Math.random().toString(36).substring(7)}@example.com`,
  password: 'SecurePassword123!',
  display_name: `Task Test User ${Date.now()}`,
});

// Test application data
const generateTestApplication = () => ({
  name: `Test App for Tasks ${Date.now()}`,
  description: 'Test application for task tests',
});

// Test project data
const generateTestProject = () => ({
  name: `Test Project for Tasks ${Date.now()}`,
  key: `TSK${Date.now().toString().slice(-4)}`.toUpperCase(),
  description: 'Test project for task tests',
  project_type: 'kanban',
});

// Test task data
const generateTestTask = (projectId: string) => ({
  project_id: projectId,
  title: `Test Task ${Date.now()}`,
  description: `Test description for task created at ${new Date().toISOString()}`,
  task_type: 'story',
  status: 'todo',
  priority: 'medium',
});

// Helper to register and login a user
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

// Helper to create full hierarchy (app -> project)
async function createTestHierarchy(
  request: APIRequestContext,
  token: string
): Promise<{ applicationId: string; projectId: string; projectKey: string }> {
  // Create application
  const appResponse = await request.post('/api/applications', {
    headers: { Authorization: `Bearer ${token}` },
    data: generateTestApplication(),
  });
  expect(appResponse.status()).toBe(201);
  const app = await appResponse.json();

  // Create project
  const projectData = generateTestProject();
  const projectResponse = await request.post(`/api/applications/${app.id}/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data: projectData,
  });
  expect(projectResponse.status()).toBe(201);
  const project = await projectResponse.json();

  return {
    applicationId: app.id,
    projectId: project.id,
    projectKey: project.key,
  };
}

// Helper to create a task
async function createTask(
  request: APIRequestContext,
  token: string,
  projectId: string,
  taskData?: Partial<ReturnType<typeof generateTestTask>>
) {
  const data = { ...generateTestTask(projectId), ...taskData, project_id: projectId };
  return request.post(`/api/projects/${projectId}/tasks`, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
}

test.describe('Tasks - Create', () => {
  let authToken: string;
  let userId: string;
  let projectId: string;
  let projectKey: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
    userId = auth.userId;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;
    projectKey = hierarchy.projectKey;
  });

  test('should create a task successfully', async ({ request }) => {
    const taskData = generateTestTask(projectId);
    const response = await createTask(request, authToken, projectId, taskData);

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.id).toBeDefined();
    expect(data.title).toBe(taskData.title);
    expect(data.description).toBe(taskData.description);
    expect(data.task_type).toBe(taskData.task_type);
    expect(data.status).toBe(taskData.status);
    expect(data.priority).toBe(taskData.priority);
    expect(data.project_id).toBe(projectId);
    expect(data.task_key).toBeDefined();
    expect(data.task_key).toContain(projectKey);
    expect(data.created_at).toBeDefined();
    expect(data.updated_at).toBeDefined();
  });

  test('should auto-generate task key with project prefix', async ({ request }) => {
    const response = await createTask(request, authToken, projectId);

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.task_key).toMatch(new RegExp(`^${projectKey}-\\d+$`));
  });

  test('should auto-increment task key numbers', async ({ request }) => {
    // Create first task
    const response1 = await createTask(request, authToken, projectId);
    const task1 = await response1.json();
    const key1Number = parseInt(task1.task_key.split('-')[1]);

    // Create second task
    const response2 = await createTask(request, authToken, projectId);
    const task2 = await response2.json();
    const key2Number = parseInt(task2.task_key.split('-')[1]);

    expect(key2Number).toBe(key1Number + 1);
  });

  test('should set reporter to current user by default', async ({ request }) => {
    const response = await createTask(request, authToken, projectId);

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.reporter_id).toBe(userId);
  });

  test('should create task with all optional fields', async ({ request }) => {
    const response = await createTask(request, authToken, projectId, {
      title: 'Full Featured Task',
      description: 'Complete description',
      task_type: 'bug',
      status: 'in_progress',
      priority: 'high',
      story_points: 5,
      due_date: '2024-12-31',
    });

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.title).toBe('Full Featured Task');
    expect(data.task_type).toBe('bug');
    expect(data.status).toBe('in_progress');
    expect(data.priority).toBe('high');
    expect(data.story_points).toBe(5);
    expect(data.due_date).toContain('2024-12-31');
  });

  test('should create task with minimum required fields', async ({ request }) => {
    const response = await createTask(request, authToken, projectId, {
      title: 'Minimal Task',
    });

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.title).toBe('Minimal Task');
    expect(data.status).toBeDefined(); // Should have default
    expect(data.priority).toBeDefined(); // Should have default
  });

  test('should create different task types', async ({ request }) => {
    const taskTypes = ['story', 'bug', 'epic', 'task', 'subtask'];

    for (const taskType of taskTypes) {
      const response = await createTask(request, authToken, projectId, {
        title: `${taskType} task`,
        task_type: taskType,
      });

      expect(response.status()).toBe(201);
      const data = await response.json();
      expect(data.task_type).toBe(taskType);
    }
  });

  test('should fail to create task without title', async ({ request }) => {
    const response = await request.post(`/api/projects/${projectId}/tasks`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {
        project_id: projectId,
        description: 'No title provided',
      },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail to create task without authentication', async ({ request }) => {
    const response = await request.post(`/api/projects/${projectId}/tasks`, {
      data: generateTestTask(projectId),
    });

    expect(response.status()).toBe(401);
  });

  test('should fail to create task in non-existent project', async ({ request }) => {
    const fakeProjectId = '00000000-0000-0000-0000-000000000000';
    const response = await createTask(request, authToken, fakeProjectId);

    expect(response.status()).toBe(404);
  });

  test('should fail to create task in another user\'s project', async ({ request }) => {
    // Create second user with their own hierarchy
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Try to create task in first user's project
    const response = await createTask(request, otherUserToken, projectId);

    expect(response.status()).toBe(403);
  });

  test('should create subtask with parent_id', async ({ request }) => {
    // Create parent task
    const parentResponse = await createTask(request, authToken, projectId, {
      title: 'Parent Task',
      task_type: 'story',
    });
    expect(parentResponse.status()).toBe(201);
    const parentTask = await parentResponse.json();

    // Create subtask
    const subtaskResponse = await createTask(request, authToken, projectId, {
      title: 'Subtask',
      task_type: 'subtask',
      parent_id: parentTask.id,
    });

    expect(subtaskResponse.status()).toBe(201);
    const subtask = await subtaskResponse.json();
    expect(subtask.parent_id).toBe(parentTask.id);
  });

  test('should fail to create subtask with non-existent parent', async ({ request }) => {
    const fakeParentId = '00000000-0000-0000-0000-000000000000';
    const response = await createTask(request, authToken, projectId, {
      title: 'Orphan Subtask',
      parent_id: fakeParentId,
    });

    expect(response.status()).toBe(400);
  });
});

test.describe('Tasks - List', () => {
  let authToken: string;
  let projectId: string;
  let createdTaskIds: string[] = [];

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;

    // Create multiple tasks for testing
    const statuses = ['todo', 'in_progress', 'done'];
    const priorities = ['low', 'medium', 'high'];
    const types = ['story', 'bug', 'task'];

    for (let i = 0; i < 9; i++) {
      const response = await createTask(request, authToken, projectId, {
        title: `List Test Task ${i + 1}`,
        status: statuses[i % 3],
        priority: priorities[i % 3],
        task_type: types[i % 3],
      });
      expect(response.status()).toBe(201);
      const task = await response.json();
      createdTaskIds.push(task.id);
    }
  });

  test('should list all tasks in a project', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}/tasks`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBeGreaterThanOrEqual(9);

    // Each task should have required fields
    data.forEach((task: any) => {
      expect(task.id).toBeDefined();
      expect(task.title).toBeDefined();
      expect(task.task_key).toBeDefined();
      expect(task.project_id).toBe(projectId);
      expect(typeof task.subtasks_count).toBe('number');
    });
  });

  test('should return tasks with subtasks_count', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}/tasks`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    data.forEach((task: any) => {
      expect(task.subtasks_count).toBeDefined();
      expect(typeof task.subtasks_count).toBe('number');
      expect(task.subtasks_count).toBeGreaterThanOrEqual(0);
    });
  });

  test('should support pagination with skip and limit', async ({ request }) => {
    // Get first 3 tasks
    const response1 = await request.get(`/api/projects/${projectId}/tasks?skip=0&limit=3`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response1.status()).toBe(200);
    const page1 = await response1.json();
    expect(page1.length).toBe(3);

    // Get next 3 tasks
    const response2 = await request.get(`/api/projects/${projectId}/tasks?skip=3&limit=3`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response2.status()).toBe(200);
    const page2 = await response2.json();
    expect(page2.length).toBe(3);

    // Pages should have different items
    expect(page1[0].id).not.toBe(page2[0].id);
  });

  test('should support search by title', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}/tasks?search=List%20Test%20Task%201`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);
    data.forEach((task: any) => {
      expect(task.title.toLowerCase()).toContain('list test task');
    });
  });

  test('should filter by status', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}/tasks?status=todo`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);
    data.forEach((task: any) => {
      expect(task.status).toBe('todo');
    });
  });

  test('should filter by priority', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}/tasks?priority=high`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);
    data.forEach((task: any) => {
      expect(task.priority).toBe('high');
    });
  });

  test('should filter by task_type', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}/tasks?task_type=bug`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);
    data.forEach((task: any) => {
      expect(task.task_type).toBe('bug');
    });
  });

  test('should combine multiple filters', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}/tasks?status=todo&priority=medium`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    data.forEach((task: any) => {
      expect(task.status).toBe('todo');
      expect(task.priority).toBe('medium');
    });
  });

  test('should fail to list tasks without authentication', async ({ request }) => {
    const response = await request.get(`/api/projects/${projectId}/tasks`);

    expect(response.status()).toBe(401);
  });

  test('should not list tasks from another user\'s project', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.get(`/api/projects/${projectId}/tasks`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });
});

test.describe('Tasks - Get by ID', () => {
  let authToken: string;
  let projectId: string;
  let taskId: string;
  let taskData: { title: string; description: string };

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;

    // Create a task
    taskData = {
      title: 'Get By ID Test Task',
      description: 'Task for get by ID tests',
    };
    const response = await createTask(request, authToken, projectId, taskData);
    expect(response.status()).toBe(201);
    const task = await response.json();
    taskId = task.id;
  });

  test('should get task by ID', async ({ request }) => {
    const response = await request.get(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.id).toBe(taskId);
    expect(data.title).toBe(taskData.title);
    expect(data.description).toBe(taskData.description);
    expect(data.project_id).toBe(projectId);
    expect(data.subtasks_count).toBeDefined();
  });

  test('should fail with non-existent task ID', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.get(`/api/tasks/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
    const data = await response.json();
    expect(data.detail).toContain('not found');
  });

  test('should fail with invalid UUID format', async ({ request }) => {
    const response = await request.get('/api/tasks/invalid-uuid', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail without authentication', async ({ request }) => {
    const response = await request.get(`/api/tasks/${taskId}`);

    expect(response.status()).toBe(401);
  });

  test('should fail accessing another user\'s task', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.get(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });
});

test.describe('Tasks - Update', () => {
  let authToken: string;
  let projectId: string;
  let taskId: string;

  test.beforeEach(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;

    // Create a fresh task for each test
    const response = await createTask(request, authToken, projectId);
    expect(response.status()).toBe(201);
    const task = await response.json();
    taskId = task.id;
  });

  test('should update task title', async ({ request }) => {
    const newTitle = `Updated Task Title ${Date.now()}`;
    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { title: newTitle },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.title).toBe(newTitle);
  });

  test('should update task description', async ({ request }) => {
    const newDescription = `Updated description at ${new Date().toISOString()}`;
    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { description: newDescription },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.description).toBe(newDescription);
  });

  test('should update task status (status transition)', async ({ request }) => {
    // todo -> in_progress
    let response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { status: 'in_progress' },
    });

    expect(response.status()).toBe(200);
    let data = await response.json();
    expect(data.status).toBe('in_progress');

    // in_progress -> in_review
    response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { status: 'in_review' },
    });

    expect(response.status()).toBe(200);
    data = await response.json();
    expect(data.status).toBe('in_review');

    // in_review -> done
    response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { status: 'done' },
    });

    expect(response.status()).toBe(200);
    data = await response.json();
    expect(data.status).toBe('done');
  });

  test('should update task priority', async ({ request }) => {
    const priorities = ['lowest', 'low', 'medium', 'high', 'highest'];

    for (const priority of priorities) {
      const response = await request.put(`/api/tasks/${taskId}`, {
        headers: { Authorization: `Bearer ${authToken}` },
        data: { priority },
      });

      expect(response.status()).toBe(200);
      const data = await response.json();
      expect(data.priority).toBe(priority);
    }
  });

  test('should update task type', async ({ request }) => {
    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { task_type: 'bug' },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.task_type).toBe('bug');
  });

  test('should update story_points', async ({ request }) => {
    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { story_points: 8 },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.story_points).toBe(8);
  });

  test('should update due_date', async ({ request }) => {
    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { due_date: '2024-12-25' },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.due_date).toContain('2024-12-25');
  });

  test('should update multiple fields at once', async ({ request }) => {
    const updates = {
      title: `Fully Updated Task ${Date.now()}`,
      description: 'Completely new description',
      status: 'in_progress',
      priority: 'high',
      story_points: 5,
    };
    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: updates,
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.title).toBe(updates.title);
    expect(data.description).toBe(updates.description);
    expect(data.status).toBe(updates.status);
    expect(data.priority).toBe(updates.priority);
    expect(data.story_points).toBe(updates.story_points);
  });

  test('should fail update with empty request body', async ({ request }) => {
    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {},
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.detail).toContain('No fields');
  });

  test('should fail update without authentication', async ({ request }) => {
    const response = await request.put(`/api/tasks/${taskId}`, {
      data: { title: 'New Title' },
    });

    expect(response.status()).toBe(401);
  });

  test('should fail to update another user\'s task', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
      data: { title: 'Hacked Title' },
    });

    expect(response.status()).toBe(403);
  });

  test('should fail to update non-existent task', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.put(`/api/tasks/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { title: 'New Title' },
    });

    expect(response.status()).toBe(404);
  });

  test('should not allow setting task as its own parent', async ({ request }) => {
    const response = await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { parent_id: taskId },
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.detail.toLowerCase()).toContain('own parent');
  });

  test('should update task key remains unchanged', async ({ request }) => {
    // Get original task key
    const getResponse = await request.get(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const originalTask = await getResponse.json();
    const originalKey = originalTask.task_key;

    // Update task
    await request.put(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { title: 'Updated Title' },
    });

    // Verify key unchanged
    const verifyResponse = await request.get(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const updatedTask = await verifyResponse.json();
    expect(updatedTask.task_key).toBe(originalKey);
  });
});

test.describe('Tasks - Delete', () => {
  let authToken: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;
  });

  test('should delete task successfully', async ({ request }) => {
    // Create a task to delete
    const createResponse = await createTask(request, authToken, projectId);
    expect(createResponse.status()).toBe(201);
    const task = await createResponse.json();

    // Delete the task
    const deleteResponse = await request.delete(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(deleteResponse.status()).toBe(204);

    // Verify it's gone
    const getResponse = await request.get(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getResponse.status()).toBe(404);
  });

  test('should cascade delete subtasks when parent is deleted', async ({ request }) => {
    // Create parent task
    const parentResponse = await createTask(request, authToken, projectId, {
      title: 'Parent to delete',
    });
    const parentTask = await parentResponse.json();

    // Create subtasks
    const subtask1Response = await createTask(request, authToken, projectId, {
      title: 'Subtask 1',
      parent_id: parentTask.id,
    });
    const subtask1 = await subtask1Response.json();

    const subtask2Response = await createTask(request, authToken, projectId, {
      title: 'Subtask 2',
      parent_id: parentTask.id,
    });
    const subtask2 = await subtask2Response.json();

    // Delete parent
    await request.delete(`/api/tasks/${parentTask.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    // Verify subtasks are also deleted
    const getSubtask1 = await request.get(`/api/tasks/${subtask1.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getSubtask1.status()).toBe(404);

    const getSubtask2 = await request.get(`/api/tasks/${subtask2.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getSubtask2.status()).toBe(404);
  });

  test('should fail delete without authentication', async ({ request }) => {
    // Create a task
    const createResponse = await createTask(request, authToken, projectId);
    const task = await createResponse.json();

    // Try to delete without auth
    const response = await request.delete(`/api/tasks/${task.id}`);

    expect(response.status()).toBe(401);
  });

  test('should fail to delete another user\'s task', async ({ request }) => {
    // Create a task
    const createResponse = await createTask(request, authToken, projectId);
    const task = await createResponse.json();

    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Try to delete with other user's token
    const response = await request.delete(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });

  test('should fail to delete non-existent task', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.delete(`/api/tasks/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });

  test('should return 404 when deleting already deleted task', async ({ request }) => {
    // Create and delete a task
    const createResponse = await createTask(request, authToken, projectId);
    const task = await createResponse.json();

    await request.delete(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    // Try to delete again
    const response = await request.delete(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });
});

test.describe('Tasks - Edge Cases', () => {
  let authToken: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;
  });

  test('should handle concurrent create requests', async ({ request }) => {
    const createPromises = Array(3)
      .fill(null)
      .map((_, i) =>
        createTask(request, authToken, projectId, {
          title: `Concurrent Task ${i + 1}`,
        })
      );

    const responses = await Promise.all(createPromises);

    // All should succeed
    responses.forEach((response) => {
      expect(response.status()).toBe(201);
    });

    // All should have unique IDs and task keys
    const tasks = await Promise.all(responses.map(async (r) => r.json()));
    const ids = new Set(tasks.map((t) => t.id));
    const keys = new Set(tasks.map((t) => t.task_key));

    expect(ids.size).toBe(3);
    expect(keys.size).toBe(3);
  });

  test('should handle Unicode characters in task data', async ({ request }) => {
    const response = await createTask(request, authToken, projectId, {
      title: 'Task \u4e2d\u6587 \ud83d\udcdd',
      description: 'Description with emoji \ud83d\udc1b and special chars \u00e9\u00e8',
    });

    expect([201, 422]).toContain(response.status());

    if (response.status() === 201) {
      const data = await response.json();
      expect(data.title).toBeDefined();
    }
  });

  test('should handle SQL injection attempts', async ({ request }) => {
    const response = await createTask(request, authToken, projectId, {
      title: "Task'; DROP TABLE Tasks; --",
      description: "Description' OR '1'='1",
    });

    // Should not cause server error
    expect(response.status()).not.toBe(500);
    expect([201, 422]).toContain(response.status());
  });

  test('should maintain task-project relationship after update', async ({ request }) => {
    // Create task
    const createResponse = await createTask(request, authToken, projectId);
    const task = await createResponse.json();

    // Update task
    await request.put(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { title: 'Updated Title' },
    });

    // Verify project_id hasn't changed
    const getResponse = await request.get(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const updatedTask = await getResponse.json();
    expect(updatedTask.project_id).toBe(projectId);
  });

  test('should handle very long task title', async ({ request }) => {
    const longTitle = 'A'.repeat(500);
    const response = await createTask(request, authToken, projectId, {
      title: longTitle,
    });

    // Should either succeed or reject with validation error, not crash
    expect([201, 422]).toContain(response.status());
  });

  test('should handle task with all null optional fields', async ({ request }) => {
    const response = await createTask(request, authToken, projectId, {
      title: 'Sparse Task',
      description: null,
      story_points: null,
      due_date: null,
      assignee_id: null,
      parent_id: null,
      sprint_id: null,
    });

    expect(response.status()).toBe(201);
    const data = await response.json();
    expect(data.title).toBe('Sparse Task');
  });

  test('should handle rapid status transitions', async ({ request }) => {
    // Create task
    const createResponse = await createTask(request, authToken, projectId);
    const task = await createResponse.json();

    // Rapid status changes
    const statuses = ['in_progress', 'in_review', 'done', 'blocked', 'todo'];

    for (const status of statuses) {
      const response = await request.put(`/api/tasks/${task.id}`, {
        headers: { Authorization: `Bearer ${authToken}` },
        data: { status },
      });
      expect(response.status()).toBe(200);
    }

    // Verify final state
    const getResponse = await request.get(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const finalTask = await getResponse.json();
    expect(finalTask.status).toBe('todo');
  });
});
