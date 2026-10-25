import { beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  applyEvent, beginScenarioSwitch, getState, hydrateMission,
  returnToLive, selectStar, setConnected, setVoiceCaption,
} from '../frontend/src/state/store.ts';

const replay = 'scenario_a_galactic_ccsn';
const sky = {
  alert_id: 'sim-reset-fixture', nside: 64, ordering: 'NESTED', frame: 'ICRS',
  prob_path: 'test-only', components: [], credible_90_deg2: 1,
  peak: { ra_deg: 0, dec_deg: 0 }, simulated: true,
};

beforeEach(() => {
  beginScenarioSwitch(replay);
  applyEvent({ type: 'alert', payload: { alert_id: sky.alert_id }, simulated: true });
  hydrateMission({ skymap: sky, simulated: true });
  selectStar('test-only-star');
  setVoiceCaption('Test replay caption', true);
  setConnected(true);
});

test('return to live clears the entire mission while keeping the app connected', () => {
  const epoch = getState().missionEpoch;
  returnToLive();
  const state = getState();
  assert.equal(state.connected, true);
  assert.equal(state.missionEpoch, epoch + 1);
  for (const field of ['scenario', 'alert', 'skymap', 'selectedStarId', 'lastSimulated']) {
    assert.equal(state[field], null, field);
  }
  assert.deepEqual(state.candidates, []);
  assert.equal(state.voiceCaption, '');
  assert.equal(state.voiceSimulated, false);
});

test('late replay packets and reconnect metadata cannot restore the dismissed selection', () => {
  returnToLive();
  for (const type of ['alert', 'skymap', 'candidates', 'voice']) {
    assert.equal(applyEvent({ type, payload: { ...sky, text: 'Old replay' }, simulated: true }), false);
  }
  assert.equal(applyEvent({ type: 'scenario_done', payload: { scenario: replay } }), false);
  applyEvent({ type: 'hello', payload: { scenario: replay } });
  assert.equal(getState().scenario, null);
  assert.equal(getState().skymap, null);
  assert.equal(getState().lastSimulated, null);
});

test('a hydrate started before reset cannot repopulate the mission', () => {
  const epoch = getState().missionEpoch;
  returnToLive();
  assert.equal(hydrateMission({ skymap: sky, expectEpoch: epoch }), false);
  assert.equal(getState().skymap, null);
});

test('a new incoming live alert is still accepted after reset', () => {
  returnToLive();
  const incoming = { ...sky, alert_id: 'new-observatory-test-fixture', simulated: false };
  assert.equal(applyEvent({ type: 'alert', payload: { alert_id: incoming.alert_id }, simulated: false }), true);
  assert.equal(applyEvent({ type: 'skymap', payload: incoming, simulated: false }), true);
  assert.equal(getState().skymap.alert_id, incoming.alert_id);
  assert.equal(getState().scenario, null);
});

test('cached replay traffic cannot undo a reset performed before its first alert', () => {
  beginScenarioSwitch('scenario_b_icecube_170922a');
  returnToLive(false);
  assert.equal(applyEvent({ type: 'alert', payload: { alert_id: 'historical-fixture' }, simulated: false }), false);
  assert.equal(getState().scenario, null);
  assert.equal(getState().alert, null);
  assert.equal(getState().skymap, null);
});

test('manually replaying the same event works again after reset', () => {
  returnToLive();
  beginScenarioSwitch(replay);
  assert.equal(applyEvent({ type: 'alert', payload: { alert_id: sky.alert_id }, simulated: true }), true);
  assert.equal(hydrateMission({ skymap: sky, expectEpoch: getState().missionEpoch }), true);
  assert.equal(getState().scenario, replay);
  assert.equal(getState().skymap.alert_id, sky.alert_id);
});
