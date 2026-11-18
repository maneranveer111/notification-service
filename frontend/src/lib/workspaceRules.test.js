import test from 'node:test';
import assert from 'node:assert/strict';
import { canDeleteWorkspace } from './workspaceRules.js';

test('owner can delete non-default workspace', () => {
  const ws = { id: '123', name: 'My Team', slug: 'my-team', deletable: true };
  assert.equal(canDeleteWorkspace(ws, 'owner'), true);
});

test('owner cannot delete default workspace', () => {
  const ws = { id: '123', name: 'Default', slug: 'default', deletable: false };
  assert.equal(canDeleteWorkspace(ws, 'owner'), false);
});

test('admin cannot delete non-default workspace', () => {
  const ws = { id: '123', name: 'My Team', slug: 'my-team', deletable: true };
  assert.equal(canDeleteWorkspace(ws, 'admin'), false);
});

test('viewer cannot delete workspace', () => {
  const ws = { id: '123', name: 'My Team', slug: 'my-team', deletable: true };
  assert.equal(canDeleteWorkspace(ws, 'viewer'), false);
});

test('null or undefined workspace returns false', () => {
  assert.equal(canDeleteWorkspace(null, 'owner'), false);
  assert.equal(canDeleteWorkspace(undefined, 'owner'), false);
});

test('invalid role returns false', () => {
  const ws = { id: '123', name: 'My Team', slug: 'my-team', deletable: true };
  assert.equal(canDeleteWorkspace(ws, null), false);
  assert.equal(canDeleteWorkspace(ws, ''), false);
  assert.equal(canDeleteWorkspace(ws, 'member'), false);
});
