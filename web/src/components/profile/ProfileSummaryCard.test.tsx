// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import ProfileSummaryCard from './ProfileSummaryCard';
import { profile } from '../../test/setup';
import { ProfileSummary } from '../../types';
const base: ProfileSummary = { profile_revision: 4, nodes: [], edges: [], recent_evidence: [], assessed_count: 1, total_count: 2, mastery_score: 80, metric_kind: 'assessed_mean', assessment_coverage: 0.5 };
it('preserves supplied score, coverage, revision and distinguishes zero from null', () => {
  const { rerender } = render(<ProfileSummaryCard profile={profile()} summary={base} activeNodeId={null} />);
  expect(screen.getByText('80%')).toBeTruthy(); expect(screen.getByText(/1 \/ 2（50%）/)).toBeTruthy(); expect(screen.getByText(/REV 4/)).toBeTruthy();
  rerender(<ProfileSummaryCard profile={profile()} summary={{ ...base, mastery_score: 0, assessment_coverage: 0 }} activeNodeId={null} />);
  expect(screen.getByText('0%')).toBeTruthy(); expect(screen.getByText(/1 \/ 2（0%）/)).toBeTruthy();
  rerender(<ProfileSummaryCard profile={profile()} summary={{ ...base, mastery_score: null, assessment_coverage: null, assessed_count: 0, total_count: 0 }} activeNodeId={null} />);
  expect(screen.getByText('待评估')).toBeTruthy(); expect(screen.getByText('暂无知识点')).toBeTruthy();
});

it('compact view shows at most three non-archived nodes with nullable mastery', () => {
  const node = (id: string, archived = false, mastery: number | null = null) => ({ id, profile_id: 'p1', title: `节点${id}`, description: '', mastery, last_practiced_at: 0, practice_count: 0, rationale: '', revision: 0, archived });
  render(<ProfileSummaryCard profile={profile()} summary={{ ...base, nodes: [node('0', true), node('1'), node('2', false, 0), node('3'), node('4')] }} activeNodeId="1" compact />);
  expect(screen.getByText('节点1：待评估')).toBeTruthy();
  expect(screen.getByText('节点2：0%')).toBeTruthy();
  expect(screen.queryByText(/节点0：/)).toBeNull();
  expect(screen.queryByText(/节点4：/)).toBeNull();
  expect(screen.getByText('当前知识点：节点1')).toBeTruthy();
});
