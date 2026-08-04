-- Retire obsolete seeded summer promotions from durable operational stores.
-- Source JSON files were removed separately; historical order pricing snapshots remain immutable.

DELETE FROM commercial_touch_events
WHERE campaign_id IN ('summer_drink', 'summer_food');

DELETE FROM analytics_event_log
WHERE payload->>'campaign_id' IN ('summer_drink', 'summer_food')
   OR payload->>'offer_id' IN ('summer_drink', 'summer_food')
   OR payload->'offer_ids' ?| ARRAY['summer_drink', 'summer_food']
   OR payload->'metadata'->>'offer_id' IN ('summer_drink', 'summer_food')
   OR payload->'metadata'->'offer_ids' ?| ARRAY['summer_drink', 'summer_food'];

DELETE FROM recommendation_events
WHERE metadata->>'offer_id' IN ('summer_drink', 'summer_food')
   OR metadata->'offer_ids' ?| ARRAY['summer_drink', 'summer_food'];

DELETE FROM recommendation_governance_events
WHERE payload->>'offer_id' IN ('summer_drink', 'summer_food')
   OR payload->'offer_ids' ?| ARRAY['summer_drink', 'summer_food'];

DELETE FROM promotion_rule_versions
WHERE promotion_id IN ('summer_drink', 'summer_food');

DELETE FROM promotion_records
WHERE promotion_id IN ('summer_drink', 'summer_food')
   OR payload->>'id' IN ('summer_drink', 'summer_food')
   OR payload->>'offer_id' IN ('summer_drink', 'summer_food')
   OR payload->>'source_id' IN ('promotion_summer_drink', 'promotion_summer_food');

DELETE FROM campaign_definitions
WHERE campaign_id IN ('summer_drink', 'summer_food');
