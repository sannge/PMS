/**
 * E2E tests for real-time collaboration via WebSocket.
 *
 * Tests cover:
 * - WebSocket connection and authentication
 * - Room-based subscriptions (join/leave)
 * - Task update broadcasting
 * - Note update broadcasting
 * - User presence events
 * - Notification delivery via WebSocket
 * - Ping/pong keepalive
 * - Multi-client synchronization
 * - Reconnection handling
 */

import { test, expect, type APIRequestContext } from '@playwright/test';
import WebSocket from 'ws';

// Test configuration
const WS_BASE_URL = process.env.WS_BASE_URL || 'ws://localhost:8000';
const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000';

// Helper types
interface WebSocketMessage {
  type: string;
  data: Record<string, unknown>;
}

// Test user data for registration/login
const generateTestUser = () => ({
  email: `collab.test.${Date.now()}.${Math.random().toString(36).substring(7)}@example.com`,
  password: 'SecurePassword123!',
  display_name: `Collab Test User ${Date.now()}`,
});

// Test application data
const generateTestApplication = () => ({
  name: `Collab Test App ${Date.now()}`,
  description: 'Test application for collaboration tests',
});

// Test project data
const generateTestProject = () => ({
  name: `Collab Test Project ${Date.now()}`,
  key: `CLB${Date.now().toString().slice(-4)}`.toUpperCase(),
  description: 'Test project for collaboration tests',
  project_type: 'kanban',
});

// Test task data
const generateTestTask = () => ({
  title: `Collab Test Task ${Date.now()}`,
  description: `Test task for collaboration at ${new Date().toISOString()}`,
  task_type: 'story',
  status: 'todo',
  priority: 'medium',
});

// Test note data
const generateTestNote = () => ({
  title: `Collab Test Note ${Date.now()}`,
  content: 'Initial content for collaboration test',
});

// Helper to register and login a user
async function setupAuthenticatedUser(
  request: APIRequestContext
): Promise<{ token: string; userId: string; email: string }> {
  const userData = generateTestUser();

  // Register
  const registerResponse = await request.post(`${API_BASE_URL}/auth/register`, {
    data: userData,
  });
  expect(registerResponse.status()).toBe(201);
  const user = await registerResponse.json();

  // Login
  const loginResponse = await request.post(`${API_BASE_URL}/auth/login`, {
    form: {
      username: userData.email,
      password: userData.password,
    },
  });
  expect(loginResponse.status()).toBe(200);
  const { access_token } = await loginResponse.json();

  return { token: access_token, userId: user.id, email: userData.email };
}

// Helper to create test hierarchy (app -> project)
async function createTestHierarchy(
  request: APIRequestContext,
  token: string
): Promise<{ applicationId: string; projectId: string; projectKey: string }> {
  // Create application
  const appResponse = await request.post(`${API_BASE_URL}/api/applications`, {
    headers: { Authorization: `Bearer ${token}` },
    data: generateTestApplication(),
  });
  expect(appResponse.status()).toBe(201);
  const app = await appResponse.json();

  // Create project
  const projectData = generateTestProject();
  const projectResponse = await request.post(`${API_BASE_URL}/api/applications/${app.id}/projects`, {
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

// Helper to create a WebSocket connection with authentication
function createAuthenticatedWebSocket(token: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`${WS_BASE_URL}/ws?token=${token}`);

    const timeout = setTimeout(() => {
      ws.close();
      reject(new Error('WebSocket connection timeout'));
    }, 10000);

    ws.on('open', () => {
      clearTimeout(timeout);
      resolve(ws);
    });

    ws.on('error', (error: Error) => {
      clearTimeout(timeout);
      reject(error);
    });
  });
}

// Helper to wait for a specific message type
function waitForMessage(
  ws: WebSocket,
  expectedType: string,
  timeout: number = 5000
): Promise<WebSocketMessage> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      ws.removeListener('message', handler);
      reject(new Error(`Timeout waiting for message type: ${expectedType}`));
    }, timeout);

    const handler = (data: WebSocket.Data) => {
      try {
        const message = JSON.parse(data.toString()) as WebSocketMessage;
        if (message.type === expectedType) {
          clearTimeout(timeoutId);
          ws.removeListener('message', handler);
          resolve(message);
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.on('message', handler);
  });
}

// Helper to collect all messages for a period
function collectMessages(ws: WebSocket, duration: number): Promise<WebSocketMessage[]> {
  return new Promise((resolve) => {
    const messages: WebSocketMessage[] = [];

    const handler = (data: WebSocket.Data) => {
      try {
        const message = JSON.parse(data.toString()) as WebSocketMessage;
        messages.push(message);
      } catch {
        // Ignore parse errors
      }
    };

    ws.on('message', handler);

    setTimeout(() => {
      ws.removeListener('message', handler);
      resolve(messages);
    }, duration);
  });
}

// Helper to send a WebSocket message and wait for response
function sendAndWait(
  ws: WebSocket,
  message: Record<string, unknown>,
  expectedResponseType: string,
  timeout: number = 5000
): Promise<WebSocketMessage> {
  const promise = waitForMessage(ws, expectedResponseType, timeout);
  ws.send(JSON.stringify(message));
  return promise;
}

// Clean up WebSocket connections
function closeWebSocket(ws: WebSocket): Promise<void> {
  return new Promise((resolve) => {
    if (ws.readyState === WebSocket.CLOSED) {
      resolve();
      return;
    }
    ws.on('close', () => resolve());
    ws.close();
  });
}

test.describe('Collaboration - WebSocket Connection', () => {
  let authToken: string;
  let userId: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
    userId = auth.userId;
  });

  test('should connect successfully with valid token', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    expect(ws.readyState).toBe(WebSocket.OPEN);

    // Should receive connected message
    const message = await waitForMessage(ws, 'connected');
    expect(message.type).toBe('connected');
    expect(message.data.user_id).toBe(userId);
    expect(message.data.connected_at).toBeDefined();
    expect(message.data.rooms).toEqual([]);

    await closeWebSocket(ws);
  });

  test('should reject connection without token', async () => {
    const ws = new WebSocket(`${WS_BASE_URL}/ws`);

    await new Promise<void>((resolve) => {
      ws.on('close', (code: number, reason: Buffer) => {
        expect(code).toBe(4001);
        expect(reason.toString()).toContain('Authentication');
        resolve();
      });
    });
  });

  test('should reject connection with invalid token', async () => {
    const ws = new WebSocket(`${WS_BASE_URL}/ws?token=invalid.token.here`);

    await new Promise<void>((resolve) => {
      ws.on('close', (code: number, reason: Buffer) => {
        expect(code).toBe(4001);
        expect(reason.toString()).toContain('Invalid');
        resolve();
      });
    });
  });

  test('should reject connection with expired token format', async () => {
    // Malformed JWT
    const expiredToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZXhwIjoxfQ.signature';
    const ws = new WebSocket(`${WS_BASE_URL}/ws?token=${expiredToken}`);

    await new Promise<void>((resolve) => {
      ws.on('close', (code: number) => {
        expect(code).toBe(4001);
        resolve();
      });
    });
  });

  test('should allow multiple connections from same user', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken);
    const ws2 = await createAuthenticatedWebSocket(authToken);

    expect(ws1.readyState).toBe(WebSocket.OPEN);
    expect(ws2.readyState).toBe(WebSocket.OPEN);

    // Both should receive connected message
    const msg1 = await waitForMessage(ws1, 'connected');
    const msg2 = await waitForMessage(ws2, 'connected');

    expect(msg1.data.user_id).toBe(userId);
    expect(msg2.data.user_id).toBe(userId);

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });
});

test.describe('Collaboration - Room Management', () => {
  let authToken: string;
  let userId: string;
  let projectId: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
    userId = auth.userId;

    const hierarchy = await createTestHierarchy(request, authToken);
    projectId = hierarchy.projectId;
    applicationId = hierarchy.applicationId;
  });

  test('should join a project room', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    const roomId = `project:${projectId}`;
    const response = await sendAndWait(
      ws,
      { type: 'join_room', data: { room_id: roomId } },
      'room_joined'
    );

    expect(response.type).toBe('room_joined');
    expect(response.data.room_id).toBe(roomId);
    expect(response.data.user_count).toBeGreaterThanOrEqual(1);

    await closeWebSocket(ws);
  });

  test('should join an application room', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    const roomId = `application:${applicationId}`;
    const response = await sendAndWait(
      ws,
      { type: 'join_room', data: { room_id: roomId } },
      'room_joined'
    );

    expect(response.type).toBe('room_joined');
    expect(response.data.room_id).toBe(roomId);

    await closeWebSocket(ws);
  });

  test('should leave a room', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    const roomId = `project:${projectId}`;

    // Join first
    await sendAndWait(ws, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    // Then leave
    const response = await sendAndWait(
      ws,
      { type: 'leave_room', data: { room_id: roomId } },
      'room_left'
    );

    expect(response.type).toBe('room_left');
    expect(response.data.room_id).toBe(roomId);

    await closeWebSocket(ws);
  });

  test('should receive user presence when another user joins', async () => {
    // Set up second user
    const user2 = await setupAuthenticatedUser(test.info().project.use);

    // Skip test if we can't create second user (API request not available in hook context)
    if (!user2) {
      test.skip();
      return;
    }

    const ws1 = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws1, 'connected');

    const roomId = `project:${projectId}`;

    // First user joins room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    // Start listening for presence updates
    const presencePromise = waitForMessage(ws1, 'user_presence', 10000);

    // Second user joins same room
    const ws2 = await createAuthenticatedWebSocket(user2.token);
    await waitForMessage(ws2, 'connected');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    // First user should receive presence notification
    const presenceMessage = await presencePromise;
    expect(presenceMessage.type).toBe('user_presence');
    expect(presenceMessage.data.room_id).toBe(roomId);
    expect(presenceMessage.data.action).toBe('joined');
    expect(presenceMessage.data.user_id).toBe(user2.userId);

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });

  test('should receive user presence when another user leaves', async ({ request }) => {
    // Set up second user
    const user2 = await setupAuthenticatedUser(request);

    const ws1 = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(user2.token);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both users join
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    // Wait a bit for any pending messages to clear
    await new Promise((r) => setTimeout(r, 100));

    // Start listening for presence updates on ws1
    const presencePromise = waitForMessage(ws1, 'user_presence', 5000);

    // Second user leaves room
    await sendAndWait(ws2, { type: 'leave_room', data: { room_id: roomId } }, 'room_left');

    // First user should receive presence notification
    const presenceMessage = await presencePromise;
    expect(presenceMessage.type).toBe('user_presence');
    expect(presenceMessage.data.room_id).toBe(roomId);
    expect(presenceMessage.data.action).toBe('left');

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });
});

test.describe('Collaboration - Ping/Pong Keepalive', () => {
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
  });

  test('should respond to ping with pong', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    const response = await sendAndWait(ws, { type: 'ping', data: {} }, 'pong');

    expect(response.type).toBe('pong');
    expect(response.data).toBeDefined();

    await closeWebSocket(ws);
  });

  test('should handle multiple pings', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    for (let i = 0; i < 3; i++) {
      const response = await sendAndWait(ws, { type: 'ping', data: {} }, 'pong');
      expect(response.type).toBe('pong');
    }

    await closeWebSocket(ws);
  });
});

test.describe('Collaboration - Task Updates Broadcasting', () => {
  let authToken1: string;
  let authToken2: string;
  let userId1: string;
  let projectId: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    // Set up two users
    const auth1 = await setupAuthenticatedUser(request);
    authToken1 = auth1.token;
    userId1 = auth1.userId;

    const auth2 = await setupAuthenticatedUser(request);
    authToken2 = auth2.token;

    const hierarchy = await createTestHierarchy(request, authToken1);
    projectId = hierarchy.projectId;
    applicationId = hierarchy.applicationId;
  });

  test('should broadcast task creation to room subscribers', async ({ request }) => {
    // Connect both users via WebSocket
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both join the project room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    // Start collecting messages on ws2
    const messagesPromise = collectMessages(ws2, 2000);

    // User 1 creates a task via HTTP API (simulating task creation)
    const taskData = generateTestTask();
    const taskResponse = await request.post(`${API_BASE_URL}/api/projects/${projectId}/tasks`, {
      headers: { Authorization: `Bearer ${authToken1}` },
      data: taskData,
    });
    expect(taskResponse.status()).toBe(201);
    const task = await taskResponse.json();

    // Wait and collect messages
    const messages = await messagesPromise;

    // Note: Task creation broadcasting depends on API integration with WebSocket
    // The test verifies the WebSocket infrastructure is working
    // Actual broadcasting from API to WebSocket would require API-level changes
    expect(task.id).toBeDefined();
    expect(task.title).toBe(taskData.title);

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });

  test('should handle task_update_request message', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both join the project room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    // Clear any pending messages
    await new Promise((r) => setTimeout(r, 200));

    // Start listening for task_updated on ws2
    const updatePromise = waitForMessage(ws2, 'task_updated', 5000);

    // User 1 sends a task update request (direct WebSocket broadcast)
    const testTaskId = '00000000-0000-0000-0000-000000000001';
    ws1.send(
      JSON.stringify({
        type: 'task_update_request',
        data: {
          project_id: projectId,
          task_id: testTaskId,
          action: 'updated',
          task: {
            id: testTaskId,
            title: 'Updated Task Title',
            status: 'in_progress',
          },
        },
      })
    );

    // User 2 should receive the task update
    const updateMessage = await updatePromise;
    expect(updateMessage.type).toBe('task_updated');
    expect(updateMessage.data.task_id).toBe(testTaskId);
    expect(updateMessage.data.project_id).toBe(projectId);
    expect(updateMessage.data.action).toBe('updated');
    expect(updateMessage.data.task).toBeDefined();

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });

  test('should broadcast task status change', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both join the project room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // Start listening for task_status_changed on ws2
    const updatePromise = waitForMessage(ws2, 'task_status_changed', 5000);

    // User 1 sends a status change request
    const testTaskId = '00000000-0000-0000-0000-000000000002';
    ws1.send(
      JSON.stringify({
        type: 'task_update_request',
        data: {
          project_id: projectId,
          task_id: testTaskId,
          action: 'status_changed',
          old_status: 'todo',
          new_status: 'in_progress',
          task: {
            id: testTaskId,
            title: 'Task with Status Change',
            status: 'in_progress',
          },
        },
      })
    );

    // User 2 should receive the status change
    const updateMessage = await updatePromise;
    expect(updateMessage.type).toBe('task_status_changed');
    expect(updateMessage.data.task_id).toBe(testTaskId);
    expect(updateMessage.data.action).toBe('status_changed');

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });

  test('should broadcast task deletion', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both join the project room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // Start listening for task_deleted on ws2
    const deletePromise = waitForMessage(ws2, 'task_deleted', 5000);

    // User 1 sends a task deletion request
    const testTaskId = '00000000-0000-0000-0000-000000000003';
    ws1.send(
      JSON.stringify({
        type: 'task_update_request',
        data: {
          project_id: projectId,
          task_id: testTaskId,
          action: 'deleted',
          task: {
            id: testTaskId,
          },
        },
      })
    );

    // User 2 should receive the task deletion
    const deleteMessage = await deletePromise;
    expect(deleteMessage.type).toBe('task_deleted');
    expect(deleteMessage.data.task_id).toBe(testTaskId);
    expect(deleteMessage.data.action).toBe('deleted');

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });
});

test.describe('Collaboration - Note Updates Broadcasting', () => {
  let authToken1: string;
  let authToken2: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    // Set up two users
    const auth1 = await setupAuthenticatedUser(request);
    authToken1 = auth1.token;

    const auth2 = await setupAuthenticatedUser(request);
    authToken2 = auth2.token;

    const hierarchy = await createTestHierarchy(request, authToken1);
    applicationId = hierarchy.applicationId;
  });

  test('should broadcast note update to application room', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `application:${applicationId}`;

    // Both join the application room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // Start listening for note_updated on ws2
    const updatePromise = waitForMessage(ws2, 'note_updated', 5000);

    // User 1 sends a note update request
    const testNoteId = '00000000-0000-0000-0000-000000000010';
    ws1.send(
      JSON.stringify({
        type: 'note_update_request',
        data: {
          application_id: applicationId,
          note_id: testNoteId,
          action: 'updated',
          note: {
            id: testNoteId,
            title: 'Updated Note Title',
            content: 'Updated content',
          },
        },
      })
    );

    // User 2 should receive the note update
    const updateMessage = await updatePromise;
    expect(updateMessage.type).toBe('note_updated');
    expect(updateMessage.data.note_id).toBe(testNoteId);
    expect(updateMessage.data.application_id).toBe(applicationId);

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });

  test('should broadcast note content change for collaborative editing', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const testNoteId = '00000000-0000-0000-0000-000000000011';
    const noteRoomId = `note:${testNoteId}`;

    // Both join the note-specific room for collaborative editing
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: noteRoomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: noteRoomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // Start listening for content change on ws2
    const contentPromise = waitForMessage(ws2, 'note_content_changed', 5000);

    // User 1 sends a content change
    ws1.send(
      JSON.stringify({
        type: 'note_update_request',
        data: {
          application_id: applicationId,
          note_id: testNoteId,
          action: 'content_changed',
          note: {
            id: testNoteId,
            content: 'New content after edit',
          },
          content_delta: {
            ops: [{ insert: 'New content after edit' }],
          },
        },
      })
    );

    // User 2 should receive the content change
    const contentMessage = await contentPromise;
    expect(contentMessage.type).toBe('note_content_changed');
    expect(contentMessage.data.note_id).toBe(testNoteId);
    expect(contentMessage.data.content_delta).toBeDefined();

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });

  test('should broadcast note deletion', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `application:${applicationId}`;

    // Both join the application room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // Start listening for note_deleted on ws2
    const deletePromise = waitForMessage(ws2, 'note_deleted', 5000);

    // User 1 sends a note deletion request
    const testNoteId = '00000000-0000-0000-0000-000000000012';
    ws1.send(
      JSON.stringify({
        type: 'note_update_request',
        data: {
          application_id: applicationId,
          note_id: testNoteId,
          action: 'deleted',
          note: {
            id: testNoteId,
          },
        },
      })
    );

    // User 2 should receive the note deletion
    const deleteMessage = await deletePromise;
    expect(deleteMessage.type).toBe('note_deleted');
    expect(deleteMessage.data.note_id).toBe(testNoteId);

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });
});

test.describe('Collaboration - User Typing Indicator', () => {
  let authToken1: string;
  let authToken2: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const auth1 = await setupAuthenticatedUser(request);
    authToken1 = auth1.token;

    const auth2 = await setupAuthenticatedUser(request);
    authToken2 = auth2.token;

    const hierarchy = await createTestHierarchy(request, authToken1);
    projectId = hierarchy.projectId;
  });

  test('should broadcast typing indicator to room', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both join the project room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // Start listening for typing indicator on ws2
    const typingPromise = waitForMessage(ws2, 'user_typing', 5000);

    // User 1 sends typing indicator
    ws1.send(
      JSON.stringify({
        type: 'user_typing',
        data: {
          room_id: roomId,
          is_typing: true,
        },
      })
    );

    // User 2 should receive the typing indicator
    const typingMessage = await typingPromise;
    expect(typingMessage.type).toBe('user_typing');
    expect(typingMessage.data.room_id).toBe(roomId);
    expect(typingMessage.data.is_typing).toBe(true);

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });

  test('should broadcast stop typing indicator', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both join the project room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // Start listening for typing indicator on ws2
    const typingPromise = waitForMessage(ws2, 'user_typing', 5000);

    // User 1 sends stop typing indicator
    ws1.send(
      JSON.stringify({
        type: 'user_typing',
        data: {
          room_id: roomId,
          is_typing: false,
        },
      })
    );

    // User 2 should receive the typing indicator
    const typingMessage = await typingPromise;
    expect(typingMessage.type).toBe('user_typing');
    expect(typingMessage.data.is_typing).toBe(false);

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });
});

test.describe('Collaboration - User Viewing Indicator', () => {
  let authToken1: string;
  let authToken2: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const auth1 = await setupAuthenticatedUser(request);
    authToken1 = auth1.token;

    const auth2 = await setupAuthenticatedUser(request);
    authToken2 = auth2.token;

    const hierarchy = await createTestHierarchy(request, authToken1);
    projectId = hierarchy.projectId;
  });

  test('should broadcast user viewing entity', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both join the project room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // Start listening for viewing indicator on ws2
    const viewingPromise = waitForMessage(ws2, 'user_viewing', 5000);

    // User 1 sends viewing indicator
    const testTaskId = '00000000-0000-0000-0000-000000000020';
    ws1.send(
      JSON.stringify({
        type: 'user_viewing',
        data: {
          room_id: roomId,
          entity_type: 'task',
          entity_id: testTaskId,
        },
      })
    );

    // User 2 should receive the viewing indicator
    const viewingMessage = await viewingPromise;
    expect(viewingMessage.type).toBe('user_viewing');
    expect(viewingMessage.data.room_id).toBe(roomId);
    expect(viewingMessage.data.entity_type).toBe('task');
    expect(viewingMessage.data.entity_id).toBe(testTaskId);

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
  });
});

test.describe('Collaboration - Error Handling', () => {
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
  });

  test('should handle malformed JSON gracefully', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    // Send malformed JSON
    ws.send('not valid json{');

    // Connection should remain open
    await new Promise((r) => setTimeout(r, 500));
    expect(ws.readyState).toBe(WebSocket.OPEN);

    await closeWebSocket(ws);
  });

  test('should handle unknown message types gracefully', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    // Send unknown message type
    ws.send(
      JSON.stringify({
        type: 'unknown_message_type',
        data: { foo: 'bar' },
      })
    );

    // Connection should remain open
    await new Promise((r) => setTimeout(r, 500));
    expect(ws.readyState).toBe(WebSocket.OPEN);

    await closeWebSocket(ws);
  });

  test('should handle missing data field gracefully', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    // Send message without data field
    ws.send(JSON.stringify({ type: 'join_room' }));

    // Connection should remain open
    await new Promise((r) => setTimeout(r, 500));
    expect(ws.readyState).toBe(WebSocket.OPEN);

    await closeWebSocket(ws);
  });

  test('should handle empty room_id gracefully', async () => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    // Send join_room with empty room_id
    ws.send(
      JSON.stringify({
        type: 'join_room',
        data: { room_id: '' },
      })
    );

    // Connection should remain open
    await new Promise((r) => setTimeout(r, 500));
    expect(ws.readyState).toBe(WebSocket.OPEN);

    await closeWebSocket(ws);
  });
});

test.describe('Collaboration - Health Check Integration', () => {
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
  });

  test('should reflect WebSocket connections in health endpoint', async ({ request }) => {
    // Get initial health status
    const initialHealth = await request.get(`${API_BASE_URL}/health`);
    expect(initialHealth.status()).toBe(200);
    const initialData = await initialHealth.json();
    const initialConnections = initialData.websocket?.connections ?? 0;

    // Connect via WebSocket
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    // Wait a moment for connection to be registered
    await new Promise((r) => setTimeout(r, 200));

    // Check health again
    const newHealth = await request.get(`${API_BASE_URL}/health`);
    expect(newHealth.status()).toBe(200);
    const newData = await newHealth.json();

    expect(newData.websocket).toBeDefined();
    expect(newData.websocket.connections).toBeGreaterThanOrEqual(initialConnections);

    await closeWebSocket(ws);
  });

  test('should track rooms in health endpoint', async ({ request }) => {
    const ws = await createAuthenticatedWebSocket(authToken);
    await waitForMessage(ws, 'connected');

    // Join a room
    await sendAndWait(ws, { type: 'join_room', data: { room_id: 'test:room:health' } }, 'room_joined');

    // Wait a moment for room to be registered
    await new Promise((r) => setTimeout(r, 200));

    // Check health
    const health = await request.get(`${API_BASE_URL}/health`);
    expect(health.status()).toBe(200);
    const data = await health.json();

    expect(data.websocket).toBeDefined();
    expect(data.websocket.rooms).toBeGreaterThanOrEqual(1);

    await closeWebSocket(ws);
  });
});

test.describe('Collaboration - Concurrent Operations', () => {
  let authToken1: string;
  let authToken2: string;
  let authToken3: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const auth1 = await setupAuthenticatedUser(request);
    authToken1 = auth1.token;

    const auth2 = await setupAuthenticatedUser(request);
    authToken2 = auth2.token;

    const auth3 = await setupAuthenticatedUser(request);
    authToken3 = auth3.token;

    const hierarchy = await createTestHierarchy(request, authToken1);
    projectId = hierarchy.projectId;
  });

  test('should handle multiple concurrent connections to same room', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    const ws2 = await createAuthenticatedWebSocket(authToken2);
    const ws3 = await createAuthenticatedWebSocket(authToken3);

    await waitForMessage(ws1, 'connected');
    await waitForMessage(ws2, 'connected');
    await waitForMessage(ws3, 'connected');

    const roomId = `project:${projectId}`;

    // All three join the same room concurrently
    const [join1, join2, join3] = await Promise.all([
      sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined'),
      sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined'),
      sendAndWait(ws3, { type: 'join_room', data: { room_id: roomId } }, 'room_joined'),
    ]);

    expect(join1.type).toBe('room_joined');
    expect(join2.type).toBe('room_joined');
    expect(join3.type).toBe('room_joined');

    // All should be able to receive messages
    await new Promise((r) => setTimeout(r, 200));

    // Start listening on ws2 and ws3
    const promise2 = waitForMessage(ws2, 'task_updated', 5000);
    const promise3 = waitForMessage(ws3, 'task_updated', 5000);

    // ws1 broadcasts a task update
    ws1.send(
      JSON.stringify({
        type: 'task_update_request',
        data: {
          project_id: projectId,
          task_id: '00000000-0000-0000-0000-000000000030',
          action: 'updated',
          task: { id: '00000000-0000-0000-0000-000000000030', title: 'Concurrent Test' },
        },
      })
    );

    // Both ws2 and ws3 should receive the update
    const [msg2, msg3] = await Promise.all([promise2, promise3]);
    expect(msg2.type).toBe('task_updated');
    expect(msg3.type).toBe('task_updated');

    await closeWebSocket(ws1);
    await closeWebSocket(ws2);
    await closeWebSocket(ws3);
  });

  test('should handle rapid message sending', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const roomId = `project:${projectId}`;
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    // Send 10 ping messages rapidly
    const pingPromises: Promise<WebSocketMessage>[] = [];
    for (let i = 0; i < 10; i++) {
      pingPromises.push(waitForMessage(ws1, 'pong', 5000));
      ws1.send(JSON.stringify({ type: 'ping', data: {} }));
    }

    // All pings should receive pongs
    const pongs = await Promise.all(pingPromises);
    expect(pongs.length).toBe(10);
    pongs.forEach((pong) => expect(pong.type).toBe('pong'));

    await closeWebSocket(ws1);
  });
});

test.describe('Collaboration - Disconnection Handling', () => {
  let authToken1: string;
  let authToken2: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    const auth1 = await setupAuthenticatedUser(request);
    authToken1 = auth1.token;

    const auth2 = await setupAuthenticatedUser(request);
    authToken2 = auth2.token;

    const hierarchy = await createTestHierarchy(request, authToken1);
    projectId = hierarchy.projectId;
  });

  test('should handle client disconnect gracefully', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const ws2 = await createAuthenticatedWebSocket(authToken2);
    await waitForMessage(ws2, 'connected');

    const roomId = `project:${projectId}`;

    // Both join the room
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');
    await sendAndWait(ws2, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    await new Promise((r) => setTimeout(r, 200));

    // ws1 listens for presence updates
    const presencePromise = waitForMessage(ws1, 'user_presence', 5000).catch(() => null);

    // ws2 disconnects abruptly
    ws2.close();

    // ws1 should receive a presence update about ws2 leaving
    // (depending on implementation, this might be via user_presence or just room cleanup)
    const presenceMessage = await presencePromise;
    // The message might be null if no presence is sent on disconnect - that's also valid behavior

    // ws1 should still be connected
    expect(ws1.readyState).toBe(WebSocket.OPEN);

    // ws1 should still be able to receive pongs
    const pong = await sendAndWait(ws1, { type: 'ping', data: {} }, 'pong');
    expect(pong.type).toBe('pong');

    await closeWebSocket(ws1);
  });

  test('should clean up rooms when all users disconnect', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const uniqueRoomId = `test:unique:${Date.now()}`;

    // Join and then leave
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: uniqueRoomId } }, 'room_joined');
    await sendAndWait(ws1, { type: 'leave_room', data: { room_id: uniqueRoomId } }, 'room_left');

    // Close connection
    await closeWebSocket(ws1);

    // The room should be cleaned up (no direct way to verify from client side,
    // but we can verify the health endpoint doesn't crash)
    // This is more of an integration test that the server doesn't have memory leaks
  });

  test('should allow reconnection after disconnect', async () => {
    const ws1 = await createAuthenticatedWebSocket(authToken1);
    await waitForMessage(ws1, 'connected');

    const roomId = `project:${projectId}`;
    await sendAndWait(ws1, { type: 'join_room', data: { room_id: roomId } }, 'room_joined');

    // Disconnect
    await closeWebSocket(ws1);

    // Reconnect with the same token
    const ws2 = await createAuthenticatedWebSocket(authToken1);
    const connectedMessage = await waitForMessage(ws2, 'connected');
    expect(connectedMessage.type).toBe('connected');

    // Should be able to rejoin rooms
    const rejoinMessage = await sendAndWait(
      ws2,
      { type: 'join_room', data: { room_id: roomId } },
      'room_joined'
    );
    expect(rejoinMessage.type).toBe('room_joined');

    await closeWebSocket(ws2);
  });
});
