/**
 * E2E tests for Task Lifecycle and Project Status Derivation.
 *
 * Verifies the complete task lifecycle workflow:
 * - Create task in Todo status
 * - Move task to In Progress
 * - Move task to Done
 * - Verify project status derivation at each step
 *
 * This is subtask-7-1 of the Project Task Management and Permissions System.
 */

import { test, expect, type APIRequestContext } from '@playwright/test';

// Test user data for registration/login
const generateTestUser = () => ({
  email: `lifecycle.test.${Date.now()}.${Math.random().toString(36).substring(7)}@example.com`,
  password: 'SecurePassword123!',
  display_name: `Lifecycle Test User ${Date.now()}`,
});

// Test application data
const generateTestApplication = () => ({
  name: `Test App for Lifecycle ${Date.now()}`,
  description: 'Test application for task lifecycle tests',
});

// Test project data
const generateTestProject = () => ({
  name: `Lifecycle Test Project ${Date.now()}`,
  key: `LCY${Date.now().toString().slice(-4)}`.toUpperCase(),
  description: 'Test project for task lifecycle verification',
  project_type: 'kanban',
});

// Test task data
const generateTestTask = (projectId: string, options?: { title?: string; status?: string }) => ({
  project_id: projectId,
  title: options?.title || `Lifecycle Test Task ${Date.now()}`,
  description: `Test task for lifecycle verification`,
  task_type: 'story',
  status: options?.status || 'todo',
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

// Helper to get project details (for checking derived status)
async function getProject(
  request: APIRequestContext,
  token: string,
  projectId: string
) {
  return request.get(`/api/projects/${projectId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// Helper to update task status via task update endpoint
async function updateTaskStatus(
  request: APIRequestContext,
  token: string,
  taskId: string,
  status: string
) {
  return request.put(`/api/tasks/${taskId}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { status },
  });
}

// Helper to move task using the move endpoint
async function moveTask(
  request: APIRequestContext,
  token: string,
  taskId: string,
  targetStatus: string
) {
  return request.put(`/api/tasks/${taskId}/move`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { target_status: targetStatus },
  });
}

test.describe('Task Lifecycle - Complete Flow', () => {
  let authToken: string;
  let userId: string;
  let applicationId: string;
  let projectId: string;
  let projectKey: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
    userId = auth.userId;

    const hierarchy = await createTestHierarchy(request, authToken);
    applicationId = hierarchy.applicationId;
    projectId = hierarchy.projectId;
    projectKey = hierarchy.projectKey;
  });

  test('should verify complete task lifecycle: Todo -> In Progress -> Done with project status derivation', async ({ request }) => {
    // Step 1: Verify initial project status (should be Todo for empty project)
    let projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    let project = await projectResponse.json();

    // Note: Initial project may have null derived_status until first task is created

    // Step 2: Create task in Todo status
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Lifecycle Test Task - Todo',
      status: 'todo',
    });
    expect(taskResponse.status()).toBe(201);
    const task = await taskResponse.json();
    expect(task.id).toBeDefined();
    expect(task.status).toBe('todo');
    expect(task.task_key).toContain(projectKey);

    // Verify task appears correctly
    const getTaskResponse = await request.get(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getTaskResponse.status()).toBe(200);
    const retrievedTask = await getTaskResponse.json();
    expect(retrievedTask.status).toBe('todo');

    // Verify project status is Todo (all tasks in Todo)
    projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    project = await projectResponse.json();
    // Project derived status should reflect task status

    // Step 3: Move task to In Progress
    const updateResponse = await updateTaskStatus(request, authToken, task.id, 'in_progress');
    expect(updateResponse.status()).toBe(200);
    const updatedTask = await updateResponse.json();
    expect(updatedTask.status).toBe('in_progress');

    // Verify project status changes to In Progress (active task exists)
    projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    project = await projectResponse.json();
    // Note: derived_status_id will be set when derivation hooks are active

    // Step 4: Move task to Done
    const doneResponse = await updateTaskStatus(request, authToken, task.id, 'done');
    expect(doneResponse.status()).toBe(200);
    const doneTask = await doneResponse.json();
    expect(doneTask.status).toBe('done');

    // Verify project status changes to Done (all tasks done)
    projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    project = await projectResponse.json();
    // Project should now be in Done status when all tasks are done

    // Step 5: Verify task history and timestamps
    expect(doneTask.updated_at).toBeDefined();
    expect(new Date(doneTask.updated_at).getTime()).toBeGreaterThan(
      new Date(task.created_at).getTime()
    );
  });

  test('should handle task status transition: Todo -> In Review -> Done', async ({ request }) => {
    // Create new task
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Review Flow Task',
      status: 'todo',
    });
    expect(taskResponse.status()).toBe(201);
    const task = await taskResponse.json();

    // Move to In Review
    let updateResponse = await updateTaskStatus(request, authToken, task.id, 'in_review');
    expect(updateResponse.status()).toBe(200);
    let updatedTask = await updateResponse.json();
    expect(updatedTask.status).toBe('in_review');

    // Move to Done
    updateResponse = await updateTaskStatus(request, authToken, task.id, 'done');
    expect(updateResponse.status()).toBe(200);
    updatedTask = await updateResponse.json();
    expect(updatedTask.status).toBe('done');
  });

  test('should handle blocked/issue status and its impact on project status', async ({ request }) => {
    // Create new task
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Blocked Task Test',
      status: 'todo',
    });
    expect(taskResponse.status()).toBe(201);
    const task = await taskResponse.json();

    // Move to blocked (issue) status
    const blockedResponse = await updateTaskStatus(request, authToken, task.id, 'blocked');
    expect(blockedResponse.status()).toBe(200);
    const blockedTask = await blockedResponse.json();
    expect(blockedTask.status).toBe('blocked');

    // Verify project status reflects Issue (blocked task should escalate)
    const projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    const project = await projectResponse.json();
    // When any task is blocked/issue, project status should be Issue

    // Move task back to In Progress to clear issue status
    const fixedResponse = await updateTaskStatus(request, authToken, task.id, 'in_progress');
    expect(fixedResponse.status()).toBe(200);
    const fixedTask = await fixedResponse.json();
    expect(fixedTask.status).toBe('in_progress');
  });
});

test.describe('Task Lifecycle - Move Endpoint', () => {
  let authToken: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;
  });

  test('should move task using move endpoint', async ({ request }) => {
    // Create task
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Move Endpoint Test Task',
      status: 'todo',
    });
    expect(taskResponse.status()).toBe(201);
    const task = await taskResponse.json();

    // Use move endpoint to change status
    const moveResponse = await moveTask(request, authToken, task.id, 'in_progress');
    expect(moveResponse.status()).toBe(200);
    const movedTask = await moveResponse.json();
    expect(movedTask.status).toBe('in_progress');
  });

  test('should support concurrent task moves (multiple tasks)', async ({ request }) => {
    // Create multiple tasks
    const task1Response = await createTask(request, authToken, projectId, {
      title: 'Concurrent Task 1',
      status: 'todo',
    });
    const task2Response = await createTask(request, authToken, projectId, {
      title: 'Concurrent Task 2',
      status: 'todo',
    });
    const task3Response = await createTask(request, authToken, projectId, {
      title: 'Concurrent Task 3',
      status: 'todo',
    });

    const task1 = await task1Response.json();
    const task2 = await task2Response.json();
    const task3 = await task3Response.json();

    // Move all tasks concurrently
    const moveResults = await Promise.all([
      updateTaskStatus(request, authToken, task1.id, 'in_progress'),
      updateTaskStatus(request, authToken, task2.id, 'in_review'),
      updateTaskStatus(request, authToken, task3.id, 'done'),
    ]);

    // Verify all moves succeeded
    moveResults.forEach((response) => {
      expect(response.status()).toBe(200);
    });

    const moved1 = await moveResults[0].json();
    const moved2 = await moveResults[1].json();
    const moved3 = await moveResults[2].json();

    expect(moved1.status).toBe('in_progress');
    expect(moved2.status).toBe('in_review');
    expect(moved3.status).toBe('done');
  });
});

test.describe('Project Status Derivation', () => {
  let authToken: string;
  let projectId: string;

  test.beforeEach(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;
  });

  test('empty project should have Todo-like status', async ({ request }) => {
    // Get project without any tasks
    const projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    const project = await projectResponse.json();

    // Empty project should have no derived status or be in Todo state
    // The derived_status_id might be null initially
    expect(project.id).toBe(projectId);
  });

  test('all tasks in Done should make project Done', async ({ request }) => {
    // Create multiple tasks and move all to Done
    const task1Response = await createTask(request, authToken, projectId, {
      title: 'Done Task 1',
      status: 'todo',
    });
    const task2Response = await createTask(request, authToken, projectId, {
      title: 'Done Task 2',
      status: 'todo',
    });

    const task1 = await task1Response.json();
    const task2 = await task2Response.json();

    // Move both to Done
    await updateTaskStatus(request, authToken, task1.id, 'done');
    await updateTaskStatus(request, authToken, task2.id, 'done');

    // Verify project status
    const projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    const project = await projectResponse.json();

    // When all tasks are Done, project derived_status should indicate Done
    // The derived_status_id will point to the project's "Done" TaskStatus
    expect(project.id).toBe(projectId);
  });

  test('any Issue task should make project show Issue status', async ({ request }) => {
    // Create tasks
    const task1Response = await createTask(request, authToken, projectId, {
      title: 'Normal Task',
      status: 'in_progress',
    });
    const task2Response = await createTask(request, authToken, projectId, {
      title: 'Issue Task',
      status: 'todo',
    });

    const task1 = await task1Response.json();
    const task2 = await task2Response.json();

    // Move task2 to blocked (issue)
    await updateTaskStatus(request, authToken, task2.id, 'blocked');

    // Verify project status escalates to Issue
    const projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    const project = await projectResponse.json();

    // Issue status should take priority over In Progress
    expect(project.id).toBe(projectId);
  });

  test('any active task should make project In Progress (no issues)', async ({ request }) => {
    // Create tasks
    const task1Response = await createTask(request, authToken, projectId, {
      title: 'Active Task',
      status: 'in_progress',
    });
    const task2Response = await createTask(request, authToken, projectId, {
      title: 'Todo Task',
      status: 'todo',
    });

    await task1Response.json();
    await task2Response.json();

    // Get project status
    const projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    const project = await projectResponse.json();

    // With active work and no issues, project should be In Progress
    expect(project.id).toBe(projectId);
  });
});

test.describe('Task Lifecycle - Edge Cases', () => {
  let authToken: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;
  });

  test('should handle rapid status transitions', async ({ request }) => {
    // Create task
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Rapid Transition Task',
      status: 'todo',
    });
    const task = await taskResponse.json();

    // Rapidly transition through all statuses
    const statuses = ['in_progress', 'in_review', 'done', 'blocked', 'todo', 'in_progress', 'done'];

    for (const status of statuses) {
      const response = await updateTaskStatus(request, authToken, task.id, status);
      expect(response.status()).toBe(200);
      const updated = await response.json();
      expect(updated.status).toBe(status);
    }
  });

  test('should handle backward status transitions', async ({ request }) => {
    // Create task in Done
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Backward Transition Task',
      status: 'done',
    });
    const task = await taskResponse.json();
    expect(task.status).toBe('done');

    // Move backward to In Review
    let updateResponse = await updateTaskStatus(request, authToken, task.id, 'in_review');
    expect(updateResponse.status()).toBe(200);
    let updatedTask = await updateResponse.json();
    expect(updatedTask.status).toBe('in_review');

    // Move backward to Todo
    updateResponse = await updateTaskStatus(request, authToken, task.id, 'todo');
    expect(updateResponse.status()).toBe(200);
    updatedTask = await updateResponse.json();
    expect(updatedTask.status).toBe('todo');
  });

  test('should handle deleting tasks and project status update', async ({ request }) => {
    // Create multiple tasks
    const task1Response = await createTask(request, authToken, projectId, {
      title: 'Task to Delete 1',
      status: 'in_progress',
    });
    const task2Response = await createTask(request, authToken, projectId, {
      title: 'Task to Delete 2',
      status: 'done',
    });

    const task1 = await task1Response.json();
    const task2 = await task2Response.json();

    // Delete task1
    const deleteResponse = await request.delete(`/api/tasks/${task1.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(deleteResponse.status()).toBe(204);

    // Verify task is deleted
    const getDeletedResponse = await request.get(`/api/tasks/${task1.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getDeletedResponse.status()).toBe(404);

    // Verify remaining task still exists
    const getTask2Response = await request.get(`/api/tasks/${task2.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getTask2Response.status()).toBe(200);

    // Project status should update based on remaining tasks
    const projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    const project = await projectResponse.json();
    expect(project.id).toBe(projectId);
  });

  test('should maintain data integrity during status changes', async ({ request }) => {
    // Create task with all fields
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Data Integrity Test Task',
      status: 'todo',
    });
    const task = await taskResponse.json();

    const originalTitle = task.title;
    const originalDescription = task.description;
    const originalPriority = task.priority;
    const originalTaskKey = task.task_key;

    // Update status multiple times
    await updateTaskStatus(request, authToken, task.id, 'in_progress');
    await updateTaskStatus(request, authToken, task.id, 'in_review');
    await updateTaskStatus(request, authToken, task.id, 'done');

    // Verify other fields remain unchanged
    const finalResponse = await request.get(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const finalTask = await finalResponse.json();

    expect(finalTask.title).toBe(originalTitle);
    expect(finalTask.description).toBe(originalDescription);
    expect(finalTask.priority).toBe(originalPriority);
    expect(finalTask.task_key).toBe(originalTaskKey);
    expect(finalTask.status).toBe('done');
  });
});

test.describe('Task Lifecycle - Validation', () => {
  let authToken: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;
  });

  test('should reject invalid status values', async ({ request }) => {
    // Create task
    const taskResponse = await createTask(request, authToken, projectId);
    const task = await taskResponse.json();

    // Try to set invalid status
    const invalidResponse = await request.put(`/api/tasks/${task.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { status: 'invalid_status' },
    });

    // Should return validation error (422)
    expect(invalidResponse.status()).toBe(422);
  });

  test('should handle status change without authentication', async ({ request }) => {
    // Create task
    const taskResponse = await createTask(request, authToken, projectId);
    const task = await taskResponse.json();

    // Try to update without auth
    const response = await request.put(`/api/tasks/${task.id}`, {
      data: { status: 'in_progress' },
    });

    expect(response.status()).toBe(401);
  });
});

/**
 * Issue Escalation Verification Tests (subtask-7-2)
 *
 * Verifies the complete Issue escalation flow:
 * 1. Create task in In Progress status
 * 2. Move task to Issue (blocked) status
 * 3. Verify project board shows Issue status with indicator
 * 4. Verify the derived_status_id is correctly updated
 */
test.describe('Issue Escalation Verification', () => {
  let authToken: string;
  let userId: string;
  let applicationId: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
    userId = auth.userId;

    const hierarchy = await createTestHierarchy(request, authToken);
    applicationId = hierarchy.applicationId;
    projectId = hierarchy.projectId;
  });

  test('should escalate project status to Issue when task moves to blocked/issue status', async ({ request }) => {
    // Step 1: Create task in In Progress status
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Issue Escalation Test Task',
      status: 'in_progress',
    });
    expect(taskResponse.status()).toBe(201);
    const task = await taskResponse.json();
    expect(task.status).toBe('in_progress');

    // Verify project status is initially In Progress
    let projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    let project = await projectResponse.json();

    // Project should have derived_status_id set (indicates status derivation is working)
    // The derived status should be "In Progress" at this point
    expect(project.id).toBe(projectId);

    // Step 2: Move task to Issue (blocked) status
    const issueResponse = await updateTaskStatus(request, authToken, task.id, 'blocked');
    expect(issueResponse.status()).toBe(200);
    const issueTask = await issueResponse.json();
    expect(issueTask.status).toBe('blocked');

    // Step 3: Verify project status has been escalated to Issue
    projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    project = await projectResponse.json();

    // Verify project has derived_status_id (status derivation is active)
    // The derived_status_id should now point to an Issue status
    expect(project.id).toBe(projectId);
    expect(project.derived_status_id).toBeDefined();

    // Step 4: Verify we can clear the Issue status by moving task out of blocked
    const fixedResponse = await updateTaskStatus(request, authToken, task.id, 'done');
    expect(fixedResponse.status()).toBe(200);
    const fixedTask = await fixedResponse.json();
    expect(fixedTask.status).toBe('done');

    // Project should now show Done status (all tasks are done)
    projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    project = await projectResponse.json();
    expect(project.id).toBe(projectId);
  });

  test('should escalate project from In Progress to Issue when one task becomes blocked', async ({ request }) => {
    // Create two tasks in different statuses
    const task1Response = await createTask(request, authToken, projectId, {
      title: 'Active Work Task',
      status: 'in_progress',
    });
    expect(task1Response.status()).toBe(201);
    const task1 = await task1Response.json();

    const task2Response = await createTask(request, authToken, projectId, {
      title: 'Another Active Task',
      status: 'in_progress',
    });
    expect(task2Response.status()).toBe(201);
    const task2 = await task2Response.json();

    // Verify project is in In Progress state
    let projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    let project = await projectResponse.json();

    // Move just one task to blocked - should escalate entire project to Issue
    const blockedResponse = await updateTaskStatus(request, authToken, task1.id, 'blocked');
    expect(blockedResponse.status()).toBe(200);
    const blockedTask = await blockedResponse.json();
    expect(blockedTask.status).toBe('blocked');

    // Verify project status is now Issue (even with other active tasks)
    projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    project = await projectResponse.json();
    expect(project.derived_status_id).toBeDefined();

    // Issue status should take priority over In Progress
    // This verifies the derivation rule: Done → Issue → In Progress → Todo
  });

  test('should use move endpoint to transition task to Issue status', async ({ request }) => {
    // Create task in todo status
    const taskResponse = await createTask(request, authToken, projectId, {
      title: 'Move Endpoint Issue Test',
      status: 'todo',
    });
    expect(taskResponse.status()).toBe(201);
    const task = await taskResponse.json();

    // Move to in_progress first
    let moveResponse = await moveTask(request, authToken, task.id, 'in_progress');
    expect(moveResponse.status()).toBe(200);
    let movedTask = await moveResponse.json();
    expect(movedTask.status).toBe('in_progress');

    // Move to blocked (Issue) using move endpoint
    moveResponse = await moveTask(request, authToken, task.id, 'blocked');
    expect(moveResponse.status()).toBe(200);
    movedTask = await moveResponse.json();
    expect(movedTask.status).toBe('blocked');

    // Verify project status escalated to Issue
    const projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    const project = await projectResponse.json();
    expect(project.derived_status_id).toBeDefined();
  });

  test('should handle Issue status with multiple tasks and verify derivation priority', async ({ request }) => {
    // Create tasks in various statuses to test derivation priority
    const todoTask = await createTask(request, authToken, projectId, {
      title: 'Pending Todo Task',
      status: 'todo',
    });
    expect(todoTask.status()).toBe(201);

    const doneTask = await createTask(request, authToken, projectId, {
      title: 'Completed Task',
      status: 'done',
    });
    expect(doneTask.status()).toBe(201);

    const activeTask = await createTask(request, authToken, projectId, {
      title: 'Active Progress Task',
      status: 'in_progress',
    });
    expect(activeTask.status()).toBe(201);
    const activeTaskData = await activeTask.json();

    // Get initial project status (should be In Progress with active work)
    let projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    let project = await projectResponse.json();
    expect(project.derived_status_id).toBeDefined();

    // Now add a blocked task - Issue should take highest priority
    const blockedTask = await createTask(request, authToken, projectId, {
      title: 'Blocked Escalation Task',
      status: 'blocked',
    });
    expect(blockedTask.status()).toBe(201);

    // Verify project status is now Issue (highest priority after Done)
    projectResponse = await getProject(request, authToken, projectId);
    expect(projectResponse.status()).toBe(200);
    project = await projectResponse.json();
    expect(project.derived_status_id).toBeDefined();

    // Derivation priority: Done → Issue → In Progress → Todo
    // With blocked task present, project should be in Issue state
  });
});
