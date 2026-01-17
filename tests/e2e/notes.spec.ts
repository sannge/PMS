/**
 * E2E tests for Notes CRUD operations.
 *
 * Tests cover:
 * - Create note within application
 * - List notes in application
 * - Get note tree (hierarchical structure)
 * - Get note by ID
 * - Get note children
 * - Update note
 * - Reorder note
 * - Delete note (with cascade and orphan options)
 * - Hierarchical note organization (parent-child relationships)
 * - Error handling
 */

import { test, expect, type APIRequestContext } from '@playwright/test';

// Test user data for registration/login
const generateTestUser = () => ({
  email: `note.test.${Date.now()}.${Math.random().toString(36).substring(7)}@example.com`,
  password: 'SecurePassword123!',
  display_name: `Note Test User ${Date.now()}`,
});

// Test application data
const generateTestApplication = () => ({
  name: `Test App for Notes ${Date.now()}`,
  description: 'Test application for note tests',
});

// Test note data
const generateTestNote = (applicationId: string) => ({
  application_id: applicationId,
  title: `Test Note ${Date.now()}`,
  content: `<p>Test content created at ${new Date().toISOString()}</p>`,
  tab_order: 0,
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

// Helper to create test application
async function createTestApplication(
  request: APIRequestContext,
  token: string
): Promise<{ applicationId: string }> {
  const appResponse = await request.post('/api/applications', {
    headers: { Authorization: `Bearer ${token}` },
    data: generateTestApplication(),
  });
  expect(appResponse.status()).toBe(201);
  const app = await appResponse.json();
  return { applicationId: app.id };
}

// Helper to create a note
async function createNote(
  request: APIRequestContext,
  token: string,
  applicationId: string,
  noteData?: Partial<ReturnType<typeof generateTestNote>>
) {
  const data = { ...generateTestNote(applicationId), ...noteData, application_id: applicationId };
  return request.post(`/api/applications/${applicationId}/notes`, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
}

test.describe('Notes - Create', () => {
  let authToken: string;
  let userId: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    const auth = await setupAuthenticatedUser(request);
    authToken = auth.token;
    userId = auth.userId;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;
  });

  test('should create a note successfully', async ({ request }) => {
    const noteData = generateTestNote(applicationId);
    const response = await createNote(request, authToken, applicationId, noteData);

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.id).toBeDefined();
    expect(data.title).toBe(noteData.title);
    expect(data.content).toBe(noteData.content);
    expect(data.application_id).toBe(applicationId);
    expect(data.created_by).toBe(userId);
    expect(data.created_at).toBeDefined();
    expect(data.updated_at).toBeDefined();
  });

  test('should create a note with minimal required fields', async ({ request }) => {
    const response = await createNote(request, authToken, applicationId, {
      title: 'Minimal Note',
    });

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.title).toBe('Minimal Note');
    expect(data.tab_order).toBeDefined(); // Should have auto-calculated tab_order
  });

  test('should auto-calculate tab_order when not provided', async ({ request }) => {
    // Create first note
    const response1 = await createNote(request, authToken, applicationId, {
      title: 'First Auto Order Note',
    });
    const note1 = await response1.json();

    // Create second note
    const response2 = await createNote(request, authToken, applicationId, {
      title: 'Second Auto Order Note',
    });
    const note2 = await response2.json();

    // Second note should have higher tab_order
    expect(note2.tab_order).toBeGreaterThan(note1.tab_order);
  });

  test('should create a note with rich text content', async ({ request }) => {
    const richContent = '<h1>Heading</h1><p><strong>Bold</strong> and <em>italic</em> text</p>';
    const response = await createNote(request, authToken, applicationId, {
      title: 'Rich Text Note',
      content: richContent,
    });

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.content).toBe(richContent);
  });

  test('should create a child note with parent_id', async ({ request }) => {
    // Create parent note
    const parentResponse = await createNote(request, authToken, applicationId, {
      title: 'Parent Note',
    });
    expect(parentResponse.status()).toBe(201);
    const parentNote = await parentResponse.json();

    // Create child note
    const childResponse = await createNote(request, authToken, applicationId, {
      title: 'Child Note',
      parent_id: parentNote.id,
    });

    expect(childResponse.status()).toBe(201);

    const childNote = await childResponse.json();
    expect(childNote.parent_id).toBe(parentNote.id);
  });

  test('should fail to create note without title', async ({ request }) => {
    const response = await request.post(`/api/applications/${applicationId}/notes`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {
        application_id: applicationId,
        content: 'Note without title',
      },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail to create note without authentication', async ({ request }) => {
    const response = await request.post(`/api/applications/${applicationId}/notes`, {
      data: generateTestNote(applicationId),
    });

    expect(response.status()).toBe(401);
  });

  test('should fail to create note in non-existent application', async ({ request }) => {
    const fakeAppId = '00000000-0000-0000-0000-000000000000';
    const response = await createNote(request, authToken, fakeAppId);

    expect(response.status()).toBe(404);
  });

  test('should fail to create note in another user\'s application', async ({ request }) => {
    // Create second user with their own application
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Try to create note in first user's application
    const response = await createNote(request, otherUserToken, applicationId);

    expect(response.status()).toBe(403);
  });

  test('should fail when application_id in body mismatches URL', async ({ request }) => {
    const fakeAppId = '00000000-0000-0000-0000-000000000000';
    const response = await request.post(`/api/applications/${applicationId}/notes`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {
        application_id: fakeAppId, // Different from URL
        title: 'Mismatch Test',
      },
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.detail.toLowerCase()).toContain('match');
  });

  test('should fail to create note with non-existent parent_id', async ({ request }) => {
    const fakeParentId = '00000000-0000-0000-0000-000000000000';
    const response = await createNote(request, authToken, applicationId, {
      title: 'Orphan Note',
      parent_id: fakeParentId,
    });

    expect(response.status()).toBe(400);
  });
});

test.describe('Notes - List', () => {
  let authToken: string;
  let applicationId: string;
  let createdNoteIds: string[] = [];

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;

    // Create multiple notes for testing
    for (let i = 0; i < 5; i++) {
      const response = await createNote(request, authToken, applicationId, {
        title: `List Test Note ${i + 1}`,
      });
      expect(response.status()).toBe(201);
      const note = await response.json();
      createdNoteIds.push(note.id);
    }
  });

  test('should list all notes in an application', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/notes`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBeGreaterThanOrEqual(5);

    // Each note should have required fields
    data.forEach((note: any) => {
      expect(note.id).toBeDefined();
      expect(note.title).toBeDefined();
      expect(note.application_id).toBe(applicationId);
      expect(typeof note.children_count).toBe('number');
    });
  });

  test('should return notes with children_count', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/notes`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    data.forEach((note: any) => {
      expect(note.children_count).toBeDefined();
      expect(typeof note.children_count).toBe('number');
      expect(note.children_count).toBeGreaterThanOrEqual(0);
    });
  });

  test('should support pagination with skip and limit', async ({ request }) => {
    // Get first 2 notes
    const response1 = await request.get(`/api/applications/${applicationId}/notes?skip=0&limit=2`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response1.status()).toBe(200);
    const page1 = await response1.json();
    expect(page1.length).toBe(2);

    // Get next 2 notes
    const response2 = await request.get(`/api/applications/${applicationId}/notes?skip=2&limit=2`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(response2.status()).toBe(200);
    const page2 = await response2.json();
    expect(page2.length).toBe(2);

    // Pages should have different items
    expect(page1[0].id).not.toBe(page2[0].id);
  });

  test('should support search by title', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/notes?search=List%20Test%20Note%201`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBeGreaterThan(0);
    data.forEach((note: any) => {
      expect(note.title.toLowerCase()).toContain('list test note');
    });
  });

  test('should filter by root_only', async ({ request }) => {
    // Create a parent note
    const parentResponse = await createNote(request, authToken, applicationId, {
      title: 'Root Only Test Parent',
    });
    const parentNote = await parentResponse.json();

    // Create a child note
    await createNote(request, authToken, applicationId, {
      title: 'Root Only Test Child',
      parent_id: parentNote.id,
    });

    // Get only root notes
    const response = await request.get(`/api/applications/${applicationId}/notes?root_only=true`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    data.forEach((note: any) => {
      expect(note.parent_id).toBeNull();
    });
  });

  test('should fail to list notes without authentication', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/notes`);

    expect(response.status()).toBe(401);
  });

  test('should not list notes from another user\'s application', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.get(`/api/applications/${applicationId}/notes`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });
});

test.describe('Notes - Get Note Tree', () => {
  let authToken: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;

    // Create a hierarchical note structure
    // Root 1
    //   Child 1.1
    //   Child 1.2
    // Root 2

    const root1Response = await createNote(request, authToken, applicationId, {
      title: 'Tree Root 1',
    });
    const root1 = await root1Response.json();

    await createNote(request, authToken, applicationId, {
      title: 'Tree Child 1.1',
      parent_id: root1.id,
    });

    await createNote(request, authToken, applicationId, {
      title: 'Tree Child 1.2',
      parent_id: root1.id,
    });

    await createNote(request, authToken, applicationId, {
      title: 'Tree Root 2',
    });
  });

  test('should return notes as hierarchical tree', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/notes/tree`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);

    // Find Root 1 and verify it has children
    const root1 = data.find((note: any) => note.title === 'Tree Root 1');
    expect(root1).toBeDefined();
    expect(root1.children).toBeDefined();
    expect(Array.isArray(root1.children)).toBe(true);
    expect(root1.children.length).toBe(2);

    // Find Root 2 and verify it has no children
    const root2 = data.find((note: any) => note.title === 'Tree Root 2');
    expect(root2).toBeDefined();
    expect(root2.children.length).toBe(0);
  });

  test('should fail to get tree without authentication', async ({ request }) => {
    const response = await request.get(`/api/applications/${applicationId}/notes/tree`);

    expect(response.status()).toBe(401);
  });
});

test.describe('Notes - Get by ID', () => {
  let authToken: string;
  let applicationId: string;
  let noteId: string;
  let noteData: { title: string; content: string };

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;

    // Create a note
    noteData = {
      title: 'Get By ID Test Note',
      content: '<p>Note for get by ID tests</p>',
    };
    const response = await createNote(request, authToken, applicationId, noteData);
    expect(response.status()).toBe(201);
    const note = await response.json();
    noteId = note.id;
  });

  test('should get note by ID', async ({ request }) => {
    const response = await request.get(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.id).toBe(noteId);
    expect(data.title).toBe(noteData.title);
    expect(data.content).toBe(noteData.content);
    expect(data.application_id).toBe(applicationId);
    expect(data.children_count).toBeDefined();
  });

  test('should fail with non-existent note ID', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.get(`/api/notes/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
    const data = await response.json();
    expect(data.detail).toContain('not found');
  });

  test('should fail with invalid UUID format', async ({ request }) => {
    const response = await request.get('/api/notes/invalid-uuid', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(422);
  });

  test('should fail without authentication', async ({ request }) => {
    const response = await request.get(`/api/notes/${noteId}`);

    expect(response.status()).toBe(401);
  });

  test('should fail accessing another user\'s note', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.get(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });
});

test.describe('Notes - Get Children', () => {
  let authToken: string;
  let applicationId: string;
  let parentNoteId: string;
  let childNoteIds: string[] = [];

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;

    // Create parent note
    const parentResponse = await createNote(request, authToken, applicationId, {
      title: 'Children Test Parent',
    });
    const parentNote = await parentResponse.json();
    parentNoteId = parentNote.id;

    // Create child notes
    for (let i = 0; i < 3; i++) {
      const childResponse = await createNote(request, authToken, applicationId, {
        title: `Children Test Child ${i + 1}`,
        parent_id: parentNoteId,
      });
      const childNote = await childResponse.json();
      childNoteIds.push(childNote.id);
    }
  });

  test('should get children of a note', async ({ request }) => {
    const response = await request.get(`/api/notes/${parentNoteId}/children`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBe(3);

    // Verify all children have correct parent_id
    data.forEach((child: any) => {
      expect(child.parent_id).toBe(parentNoteId);
      expect(child.children_count).toBeDefined();
    });
  });

  test('should return empty array for note with no children', async ({ request }) => {
    // Use one of the child notes (which has no children)
    const response = await request.get(`/api/notes/${childNoteIds[0]}/children`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBe(0);
  });

  test('should support pagination for children', async ({ request }) => {
    const response = await request.get(`/api/notes/${parentNoteId}/children?skip=0&limit=2`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.length).toBe(2);
  });
});

test.describe('Notes - Update', () => {
  let authToken: string;
  let applicationId: string;
  let noteId: string;

  test.beforeEach(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;

    // Create a fresh note for each test
    const response = await createNote(request, authToken, applicationId);
    expect(response.status()).toBe(201);
    const note = await response.json();
    noteId = note.id;
  });

  test('should update note title', async ({ request }) => {
    const newTitle = `Updated Note Title ${Date.now()}`;
    const response = await request.put(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { title: newTitle },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.title).toBe(newTitle);
  });

  test('should update note content', async ({ request }) => {
    const newContent = `<p>Updated content at ${new Date().toISOString()}</p>`;
    const response = await request.put(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { content: newContent },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.content).toBe(newContent);
  });

  test('should update note tab_order', async ({ request }) => {
    const response = await request.put(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { tab_order: 5 },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.tab_order).toBe(5);
  });

  test('should update multiple fields at once', async ({ request }) => {
    const updates = {
      title: `Fully Updated Note ${Date.now()}`,
      content: '<p>Completely new content</p>',
      tab_order: 10,
    };
    const response = await request.put(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: updates,
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.title).toBe(updates.title);
    expect(data.content).toBe(updates.content);
    expect(data.tab_order).toBe(updates.tab_order);
  });

  test('should fail update with empty request body', async ({ request }) => {
    const response = await request.put(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: {},
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.detail).toContain('No fields');
  });

  test('should fail update without authentication', async ({ request }) => {
    const response = await request.put(`/api/notes/${noteId}`, {
      data: { title: 'New Title' },
    });

    expect(response.status()).toBe(401);
  });

  test('should fail to update another user\'s note', async ({ request }) => {
    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    const response = await request.put(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
      data: { title: 'Hacked Title' },
    });

    expect(response.status()).toBe(403);
  });

  test('should fail to update non-existent note', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.put(`/api/notes/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { title: 'New Title' },
    });

    expect(response.status()).toBe(404);
  });

  test('should not allow setting note as its own parent', async ({ request }) => {
    const response = await request.put(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { parent_id: noteId },
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.detail.toLowerCase()).toContain('own parent');
  });

  test('should move note to new parent', async ({ request }) => {
    // Create a new potential parent note
    const parentResponse = await createNote(request, authToken, applicationId, {
      title: 'New Parent Note',
    });
    const parentNote = await parentResponse.json();

    // Update note's parent
    const response = await request.put(`/api/notes/${noteId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { parent_id: parentNote.id },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.parent_id).toBe(parentNote.id);
  });
});

test.describe('Notes - Reorder', () => {
  let authToken: string;
  let applicationId: string;
  let noteIds: string[] = [];

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;

    // Create multiple notes for reordering tests
    for (let i = 0; i < 3; i++) {
      const response = await createNote(request, authToken, applicationId, {
        title: `Reorder Test Note ${i + 1}`,
        tab_order: i,
      });
      const note = await response.json();
      noteIds.push(note.id);
    }
  });

  test('should reorder a note', async ({ request }) => {
    const response = await request.put(`/api/notes/${noteIds[0]}/reorder?new_order=2`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.tab_order).toBe(2);
  });

  test('should return same note when order unchanged', async ({ request }) => {
    // First get the current order
    const getResponse = await request.get(`/api/notes/${noteIds[1]}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const note = await getResponse.json();
    const currentOrder = note.tab_order;

    // Reorder to same position
    const response = await request.put(`/api/notes/${noteIds[1]}/reorder?new_order=${currentOrder}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.tab_order).toBe(currentOrder);
  });
});

test.describe('Notes - Delete', () => {
  let authToken: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;
  });

  test('should delete note successfully', async ({ request }) => {
    // Create a note to delete
    const createResponse = await createNote(request, authToken, applicationId);
    expect(createResponse.status()).toBe(201);
    const note = await createResponse.json();

    // Delete the note
    const deleteResponse = await request.delete(`/api/notes/${note.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(deleteResponse.status()).toBe(204);

    // Verify it's gone
    const getResponse = await request.get(`/api/notes/${note.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getResponse.status()).toBe(404);
  });

  test('should cascade delete children by default', async ({ request }) => {
    // Create parent note
    const parentResponse = await createNote(request, authToken, applicationId, {
      title: 'Parent to delete',
    });
    const parentNote = await parentResponse.json();

    // Create child notes
    const child1Response = await createNote(request, authToken, applicationId, {
      title: 'Child 1',
      parent_id: parentNote.id,
    });
    const child1 = await child1Response.json();

    const child2Response = await createNote(request, authToken, applicationId, {
      title: 'Child 2',
      parent_id: parentNote.id,
    });
    const child2 = await child2Response.json();

    // Delete parent (default cascade=true)
    await request.delete(`/api/notes/${parentNote.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    // Verify children are also deleted
    const getChild1 = await request.get(`/api/notes/${child1.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getChild1.status()).toBe(404);

    const getChild2 = await request.get(`/api/notes/${child2.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getChild2.status()).toBe(404);
  });

  test('should orphan children when cascade=false', async ({ request }) => {
    // Create parent note
    const parentResponse = await createNote(request, authToken, applicationId, {
      title: 'Parent to orphan',
    });
    const parentNote = await parentResponse.json();

    // Create child note
    const childResponse = await createNote(request, authToken, applicationId, {
      title: 'Child to orphan',
      parent_id: parentNote.id,
    });
    const childNote = await childResponse.json();

    // Delete parent with cascade=false
    await request.delete(`/api/notes/${parentNote.id}?cascade=false`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    // Verify child still exists but is now orphaned
    const getChild = await request.get(`/api/notes/${childNote.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(getChild.status()).toBe(200);

    const orphanedChild = await getChild.json();
    expect(orphanedChild.parent_id).toBeNull();
  });

  test('should fail delete without authentication', async ({ request }) => {
    // Create a note
    const createResponse = await createNote(request, authToken, applicationId);
    const note = await createResponse.json();

    // Try to delete without auth
    const response = await request.delete(`/api/notes/${note.id}`);

    expect(response.status()).toBe(401);
  });

  test('should fail to delete another user\'s note', async ({ request }) => {
    // Create a note
    const createResponse = await createNote(request, authToken, applicationId);
    const note = await createResponse.json();

    // Create second user
    const { token: otherUserToken } = await setupAuthenticatedUser(request);

    // Try to delete with other user's token
    const response = await request.delete(`/api/notes/${note.id}`, {
      headers: { Authorization: `Bearer ${otherUserToken}` },
    });

    expect(response.status()).toBe(403);
  });

  test('should fail to delete non-existent note', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const response = await request.delete(`/api/notes/${fakeId}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });

  test('should return 404 when deleting already deleted note', async ({ request }) => {
    // Create and delete a note
    const createResponse = await createNote(request, authToken, applicationId);
    const note = await createResponse.json();

    await request.delete(`/api/notes/${note.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    // Try to delete again
    const response = await request.delete(`/api/notes/${note.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(404);
  });
});

test.describe('Notes - Edge Cases', () => {
  let authToken: string;
  let applicationId: string;

  test.beforeAll(async ({ request }) => {
    const { token } = await setupAuthenticatedUser(request);
    authToken = token;

    const app = await createTestApplication(request, authToken);
    applicationId = app.applicationId;
  });

  test('should handle concurrent create requests', async ({ request }) => {
    const createPromises = Array(3)
      .fill(null)
      .map((_, i) =>
        createNote(request, authToken, applicationId, {
          title: `Concurrent Note ${i + 1}`,
        })
      );

    const responses = await Promise.all(createPromises);

    // All should succeed
    responses.forEach((response) => {
      expect(response.status()).toBe(201);
    });

    // All should have unique IDs
    const notes = await Promise.all(responses.map(async (r) => r.json()));
    const ids = new Set(notes.map((n) => n.id));
    expect(ids.size).toBe(3);
  });

  test('should handle Unicode characters in note data', async ({ request }) => {
    const response = await createNote(request, authToken, applicationId, {
      title: 'Note \u4e2d\u6587 \ud83d\udcdd',
      content: '<p>Content with emoji \ud83d\udc1b and special chars \u00e9\u00e8</p>',
    });

    expect([201, 422]).toContain(response.status());

    if (response.status() === 201) {
      const data = await response.json();
      expect(data.title).toBeDefined();
    }
  });

  test('should handle SQL injection attempts', async ({ request }) => {
    const response = await createNote(request, authToken, applicationId, {
      title: "Note'; DROP TABLE Notes; --",
      content: "<p>Content' OR '1'='1</p>",
    });

    // Should not cause server error
    expect(response.status()).not.toBe(500);
    expect([201, 422]).toContain(response.status());
  });

  test('should handle very long note title', async ({ request }) => {
    const longTitle = 'A'.repeat(255);
    const response = await createNote(request, authToken, applicationId, {
      title: longTitle,
    });

    // Should either succeed or reject with validation error, not crash
    expect([201, 422]).toContain(response.status());
  });

  test('should handle very long note content', async ({ request }) => {
    const longContent = '<p>' + 'A'.repeat(10000) + '</p>';
    const response = await createNote(request, authToken, applicationId, {
      title: 'Long Content Note',
      content: longContent,
    });

    // Should succeed (NVARCHAR(MAX) in database)
    expect(response.status()).toBe(201);
  });

  test('should maintain note-application relationship after update', async ({ request }) => {
    // Create note
    const createResponse = await createNote(request, authToken, applicationId);
    const note = await createResponse.json();

    // Update note
    await request.put(`/api/notes/${note.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
      data: { title: 'Updated Title' },
    });

    // Verify application_id hasn't changed
    const getResponse = await request.get(`/api/notes/${note.id}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const updatedNote = await getResponse.json();
    expect(updatedNote.application_id).toBe(applicationId);
  });

  test('should handle deep note hierarchy', async ({ request }) => {
    // Create a 3-level deep hierarchy
    const level1Response = await createNote(request, authToken, applicationId, {
      title: 'Level 1',
    });
    const level1 = await level1Response.json();

    const level2Response = await createNote(request, authToken, applicationId, {
      title: 'Level 2',
      parent_id: level1.id,
    });
    const level2 = await level2Response.json();

    const level3Response = await createNote(request, authToken, applicationId, {
      title: 'Level 3',
      parent_id: level2.id,
    });
    const level3 = await level3Response.json();

    // Verify hierarchy
    expect(level2.parent_id).toBe(level1.id);
    expect(level3.parent_id).toBe(level2.id);

    // Get tree and verify structure
    const treeResponse = await request.get(`/api/applications/${applicationId}/notes/tree`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const tree = await treeResponse.json();

    const foundLevel1 = tree.find((n: any) => n.id === level1.id);
    expect(foundLevel1).toBeDefined();
    expect(foundLevel1.children.length).toBeGreaterThan(0);
  });
});
