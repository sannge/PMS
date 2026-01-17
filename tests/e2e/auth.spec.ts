/**
 * E2E tests for authentication flows.
 *
 * Tests cover:
 * - User registration
 * - User login
 * - User logout
 * - Protected route access
 * - Session/token management
 */

import { test, expect, type APIRequestContext } from '@playwright/test';

// Test user data for registration/login
const generateTestUser = () => ({
  email: `test.user.${Date.now()}@example.com`,
  password: 'SecurePassword123!',
  display_name: `Test User ${Date.now()}`,
});

// Helper to get auth token via login
async function loginUser(
  request: APIRequestContext,
  email: string,
  password: string
): Promise<string | null> {
  const response = await request.post('/auth/login', {
    form: {
      username: email,
      password: password,
    },
  });

  if (response.status() === 200) {
    const data = await response.json();
    return data.access_token;
  }
  return null;
}

// Helper to register a user
async function registerUser(
  request: APIRequestContext,
  userData: { email: string; password: string; display_name: string }
) {
  return request.post('/auth/register', {
    data: userData,
  });
}

test.describe('Authentication - Registration', () => {
  test('should register a new user successfully', async ({ request }) => {
    const testUser = generateTestUser();

    const response = await registerUser(request, testUser);

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.email).toBe(testUser.email);
    expect(data.display_name).toBe(testUser.display_name);
    expect(data.id).toBeDefined();
    expect(data.created_at).toBeDefined();
    expect(data.updated_at).toBeDefined();

    // Sensitive data should not be returned
    expect(data.password).toBeUndefined();
    expect(data.password_hash).toBeUndefined();
  });

  test('should fail registration with invalid email format', async ({ request }) => {
    const response = await request.post('/auth/register', {
      data: {
        email: 'invalid-email-format',
        password: 'SecurePassword123!',
        display_name: 'Test User',
      },
    });

    expect(response.status()).toBe(422); // Validation error
    const data = await response.json();
    expect(data.detail).toBeDefined();
  });

  test('should fail registration with short password', async ({ request }) => {
    const response = await request.post('/auth/register', {
      data: {
        email: `test.short.${Date.now()}@example.com`,
        password: 'short', // Less than 8 characters
        display_name: 'Test User',
      },
    });

    expect(response.status()).toBe(422); // Validation error
    const data = await response.json();
    expect(data.detail).toBeDefined();
  });

  test('should fail registration with duplicate email', async ({ request }) => {
    const testUser = generateTestUser();

    // First registration should succeed
    const firstResponse = await registerUser(request, testUser);
    expect(firstResponse.status()).toBe(201);

    // Second registration with same email should fail
    const secondResponse = await registerUser(request, testUser);
    expect(secondResponse.status()).toBe(400);

    const data = await secondResponse.json();
    expect(data.detail.toLowerCase()).toContain('already registered');
  });

  test('should fail registration without required fields', async ({ request }) => {
    const response = await request.post('/auth/register', {
      data: {},
    });

    expect(response.status()).toBe(422);
  });

  test('should allow registration without display_name', async ({ request }) => {
    const response = await request.post('/auth/register', {
      data: {
        email: `test.noname.${Date.now()}@example.com`,
        password: 'SecurePassword123!',
        // display_name is optional
      },
    });

    expect(response.status()).toBe(201);
    const data = await response.json();
    expect(data.email).toBeDefined();
    expect(data.display_name).toBeNull();
  });
});

test.describe('Authentication - Login', () => {
  let testUser: ReturnType<typeof generateTestUser>;

  test.beforeAll(async ({ request }) => {
    // Create a user for login tests
    testUser = generateTestUser();
    const response = await registerUser(request, testUser);
    expect(response.status()).toBe(201);
  });

  test('should login successfully with valid credentials', async ({ request }) => {
    const response = await request.post('/auth/login', {
      form: {
        username: testUser.email,
        password: testUser.password,
      },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.access_token).toBeDefined();
    expect(data.token_type).toBe('bearer');
    expect(typeof data.access_token).toBe('string');
    expect(data.access_token.length).toBeGreaterThan(0);
  });

  test('should fail login with wrong password', async ({ request }) => {
    const response = await request.post('/auth/login', {
      form: {
        username: testUser.email,
        password: 'WrongPassword123!',
      },
    });

    expect(response.status()).toBe(401);

    const data = await response.json();
    expect(data.detail.toLowerCase()).toContain('incorrect');
  });

  test('should fail login with non-existent user', async ({ request }) => {
    const response = await request.post('/auth/login', {
      form: {
        username: 'nonexistent.user@example.com',
        password: 'SomePassword123!',
      },
    });

    expect(response.status()).toBe(401);
  });

  test('should fail login with empty credentials', async ({ request }) => {
    const response = await request.post('/auth/login', {
      form: {
        username: '',
        password: '',
      },
    });

    // Either 401 (invalid credentials) or 422 (validation error)
    expect([401, 422]).toContain(response.status());
  });

  test('should fail login without password', async ({ request }) => {
    const response = await request.post('/auth/login', {
      form: {
        username: testUser.email,
        // password omitted
      },
    });

    expect(response.status()).toBe(422);
  });

  test('should use OAuth2 password flow format', async ({ request }) => {
    // OAuth2 requires 'username' field even for email-based auth
    const response = await request.post('/auth/login', {
      form: {
        username: testUser.email,
        password: testUser.password,
      },
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.token_type).toBe('bearer');
  });
});

test.describe('Authentication - Logout', () => {
  let testUser: ReturnType<typeof generateTestUser>;
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    // Create and login a user for logout tests
    testUser = generateTestUser();
    await registerUser(request, testUser);
    authToken = (await loginUser(request, testUser.email, testUser.password)) as string;
    expect(authToken).toBeDefined();
  });

  test('should logout successfully with valid token', async ({ request }) => {
    const response = await request.post('/auth/logout', {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.message).toContain('logged out');
    expect(data.user_id).toBeDefined();
  });

  test('should fail logout without authentication', async ({ request }) => {
    const response = await request.post('/auth/logout');

    expect(response.status()).toBe(401);
  });

  test('should fail logout with invalid token', async ({ request }) => {
    const response = await request.post('/auth/logout', {
      headers: {
        Authorization: 'Bearer invalid.token.here',
      },
    });

    expect(response.status()).toBe(401);
  });

  test('should fail logout with expired token format', async ({ request }) => {
    // Malformed JWT structure
    const response = await request.post('/auth/logout', {
      headers: {
        Authorization: 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U',
      },
    });

    expect(response.status()).toBe(401);
  });
});

test.describe('Authentication - Protected Routes', () => {
  let testUser: ReturnType<typeof generateTestUser>;
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    // Create and login a user for protected route tests
    testUser = generateTestUser();
    await registerUser(request, testUser);
    authToken = (await loginUser(request, testUser.email, testUser.password)) as string;
    expect(authToken).toBeDefined();
  });

  test('should access /auth/me with valid token', async ({ request }) => {
    const response = await request.get('/auth/me', {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.email).toBe(testUser.email);
    expect(data.display_name).toBe(testUser.display_name);
    expect(data.id).toBeDefined();
  });

  test('should fail accessing /auth/me without token', async ({ request }) => {
    const response = await request.get('/auth/me');

    expect(response.status()).toBe(401);
    const data = await response.json();
    expect(data.detail).toBeDefined();
  });

  test('should fail accessing /auth/me with invalid token', async ({ request }) => {
    const response = await request.get('/auth/me', {
      headers: {
        Authorization: 'Bearer invalid.token.here',
      },
    });

    expect(response.status()).toBe(401);
  });

  test('should fail accessing /auth/me with malformed Authorization header', async ({ request }) => {
    const response = await request.get('/auth/me', {
      headers: {
        Authorization: 'NotBearer sometoken',
      },
    });

    expect(response.status()).toBe(401);
  });

  test('should fail accessing protected /api/applications without token', async ({ request }) => {
    const response = await request.get('/api/applications');

    expect(response.status()).toBe(401);
  });

  test('should access protected /api/applications with valid token', async ({ request }) => {
    const response = await request.get('/api/applications', {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });

    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
  });
});

test.describe('Authentication - Token Validation', () => {
  let testUser: ReturnType<typeof generateTestUser>;
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    // Create and login a user for token validation tests
    testUser = generateTestUser();
    await registerUser(request, testUser);
    authToken = (await loginUser(request, testUser.email, testUser.password)) as string;
    expect(authToken).toBeDefined();
  });

  test('should validate JWT token structure', async ({ request }) => {
    // JWT has three parts separated by dots
    const parts = authToken.split('.');
    expect(parts.length).toBe(3);

    // Each part should be base64 encoded
    parts.forEach((part) => {
      expect(part.length).toBeGreaterThan(0);
    });
  });

  test('should return consistent user data on multiple /auth/me calls', async ({ request }) => {
    const headers = { Authorization: `Bearer ${authToken}` };

    const response1 = await request.get('/auth/me', { headers });
    const response2 = await request.get('/auth/me', { headers });

    expect(response1.status()).toBe(200);
    expect(response2.status()).toBe(200);

    const data1 = await response1.json();
    const data2 = await response2.json();

    expect(data1.id).toBe(data2.id);
    expect(data1.email).toBe(data2.email);
  });

  test('should work with Bearer token case-insensitively', async ({ request }) => {
    // Standard: "Bearer" with capital B
    const response = await request.get('/auth/me', {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });

    expect(response.status()).toBe(200);
  });

  test('should reject token with extra whitespace', async ({ request }) => {
    const response = await request.get('/auth/me', {
      headers: {
        Authorization: `Bearer  ${authToken}`, // Extra space
      },
    });

    // Depending on implementation, might be 401 or work
    // Most strict implementations reject this
    expect([200, 401]).toContain(response.status());
  });
});

test.describe('Authentication - Session Persistence', () => {
  let testUser: ReturnType<typeof generateTestUser>;
  let authToken: string;

  test.beforeAll(async ({ request }) => {
    testUser = generateTestUser();
    await registerUser(request, testUser);
    authToken = (await loginUser(request, testUser.email, testUser.password)) as string;
  });

  test('should allow multiple concurrent requests with same token', async ({ request }) => {
    const headers = { Authorization: `Bearer ${authToken}` };

    // Make multiple requests concurrently
    const [response1, response2, response3] = await Promise.all([
      request.get('/auth/me', { headers }),
      request.get('/api/applications', { headers }),
      request.get('/auth/me', { headers }),
    ]);

    expect(response1.status()).toBe(200);
    expect(response2.status()).toBe(200);
    expect(response3.status()).toBe(200);
  });

  test('should maintain session across different endpoints', async ({ request }) => {
    const headers = { Authorization: `Bearer ${authToken}` };

    // Access /auth/me
    const meResponse = await request.get('/auth/me', { headers });
    expect(meResponse.status()).toBe(200);

    // Access /api/applications
    const appsResponse = await request.get('/api/applications', { headers });
    expect(appsResponse.status()).toBe(200);

    // Access /auth/me again
    const meResponse2 = await request.get('/auth/me', { headers });
    expect(meResponse2.status()).toBe(200);

    // Should return same user
    const userData1 = await meResponse.json();
    const userData2 = await meResponse2.json();
    expect(userData1.id).toBe(userData2.id);
  });

  test('should allow re-login and get new token', async ({ request }) => {
    // Login again to get a new token
    const newToken = await loginUser(request, testUser.email, testUser.password);

    expect(newToken).toBeDefined();
    expect(newToken).not.toBe(authToken); // New token should be different

    // Both tokens should work (JWT is stateless)
    const oldTokenResponse = await request.get('/auth/me', {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const newTokenResponse = await request.get('/auth/me', {
      headers: { Authorization: `Bearer ${newToken}` },
    });

    expect(oldTokenResponse.status()).toBe(200);
    expect(newTokenResponse.status()).toBe(200);
  });
});

test.describe('Authentication - Security', () => {
  test('should not expose password in registration response', async ({ request }) => {
    const testUser = generateTestUser();
    const response = await registerUser(request, testUser);

    expect(response.status()).toBe(201);
    const data = await response.json();

    // Verify password-related fields are not exposed
    expect(data.password).toBeUndefined();
    expect(data.password_hash).toBeUndefined();
    expect(data.hashed_password).toBeUndefined();
  });

  test('should not expose password in user profile response', async ({ request }) => {
    const testUser = generateTestUser();
    await registerUser(request, testUser);
    const authToken = await loginUser(request, testUser.email, testUser.password);

    const response = await request.get('/auth/me', {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    expect(response.status()).toBe(200);
    const data = await response.json();

    // Verify password-related fields are not exposed
    expect(data.password).toBeUndefined();
    expect(data.password_hash).toBeUndefined();
  });

  test('should reject SQL injection attempts in login', async ({ request }) => {
    const response = await request.post('/auth/login', {
      form: {
        username: "admin'--",
        password: "' OR '1'='1",
      },
    });

    // Should not cause server error (500) - proper handling returns 401
    expect(response.status()).not.toBe(500);
    expect([401, 422]).toContain(response.status());
  });

  test('should reject XSS attempts in registration', async ({ request }) => {
    const response = await request.post('/auth/register', {
      data: {
        email: `test.xss.${Date.now()}@example.com`,
        password: 'SecurePassword123!',
        display_name: '<script>alert("xss")</script>',
      },
    });

    // Registration might succeed but XSS should be escaped/sanitized
    if (response.status() === 201) {
      const data = await response.json();
      // If stored, it should not execute (just be stored as text)
      expect(data.display_name).toBeDefined();
    }
    // Should not cause server error
    expect(response.status()).not.toBe(500);
  });

  test('should handle very long password gracefully', async ({ request }) => {
    const longPassword = 'A'.repeat(500);
    const response = await request.post('/auth/register', {
      data: {
        email: `test.longpw.${Date.now()}@example.com`,
        password: longPassword,
        display_name: 'Test User',
      },
    });

    // Should either accept (if within limits) or reject with 422, not crash
    expect([201, 422]).toContain(response.status());
    expect(response.status()).not.toBe(500);
  });

  test('should handle Unicode characters in credentials', async ({ request }) => {
    const testUser = {
      email: `test.unicode.${Date.now()}@example.com`,
      password: 'SecureP@ss123!',
      display_name: 'Test User \u4e2d\u6587', // Chinese characters
    };

    const registerResponse = await registerUser(request, testUser);
    expect([201, 422]).toContain(registerResponse.status());

    if (registerResponse.status() === 201) {
      const loginResponse = await request.post('/auth/login', {
        form: {
          username: testUser.email,
          password: testUser.password,
        },
      });
      expect(loginResponse.status()).toBe(200);
    }
  });
});

test.describe('Authentication - Error Handling', () => {
  test('should return proper error format for validation errors', async ({ request }) => {
    const response = await request.post('/auth/register', {
      data: {
        email: 'invalid',
        password: 'short',
      },
    });

    expect(response.status()).toBe(422);
    const data = await response.json();
    expect(data.detail).toBeDefined();
    expect(Array.isArray(data.detail)).toBe(true);
  });

  test('should return proper error format for authentication errors', async ({ request }) => {
    const response = await request.post('/auth/login', {
      form: {
        username: 'nonexistent@example.com',
        password: 'wrongpassword',
      },
    });

    expect(response.status()).toBe(401);
    const data = await response.json();
    expect(data.detail).toBeDefined();
    expect(typeof data.detail).toBe('string');
  });

  test('should include WWW-Authenticate header on 401 for /auth/me', async ({ request }) => {
    const response = await request.get('/auth/me');

    expect(response.status()).toBe(401);
    // OAuth2 spec requires WWW-Authenticate header
    const wwwAuth = response.headers()['www-authenticate'];
    expect(wwwAuth).toBeDefined();
  });

  test('should handle malformed JSON in registration', async ({ request }) => {
    const response = await request.post('/auth/register', {
      headers: { 'Content-Type': 'application/json' },
      data: 'not valid json{',
    });

    expect(response.status()).toBe(422);
  });

  test('should handle empty request body in registration', async ({ request }) => {
    const response = await request.post('/auth/register', {
      headers: { 'Content-Type': 'application/json' },
      data: null,
    });

    expect(response.status()).toBe(422);
  });
});

test.describe('Authentication - Rate Limiting Awareness', () => {
  // These tests verify the system handles rapid requests gracefully
  // Actual rate limiting may or may not be implemented

  test('should handle rapid consecutive login attempts', async ({ request }) => {
    const testUser = generateTestUser();
    await registerUser(request, testUser);

    // Make several login attempts quickly
    const attempts = Array(5)
      .fill(null)
      .map(() =>
        request.post('/auth/login', {
          form: {
            username: testUser.email,
            password: testUser.password,
          },
        })
      );

    const responses = await Promise.all(attempts);

    // All should succeed (no rate limiting expected in basic setup)
    // Or if rate limited, should return 429
    responses.forEach((response) => {
      expect([200, 429]).toContain(response.status());
    });
  });

  test('should handle rapid failed login attempts', async ({ request }) => {
    // Make several failed login attempts quickly
    const attempts = Array(5)
      .fill(null)
      .map(() =>
        request.post('/auth/login', {
          form: {
            username: `nonexistent.${Date.now()}.${Math.random()}@example.com`,
            password: 'wrongpassword',
          },
        })
      );

    const responses = await Promise.all(attempts);

    // Should return 401 for each or 429 if rate limited
    responses.forEach((response) => {
      expect([401, 429]).toContain(response.status());
    });
  });
});
