# X v2-009 Test Account Publish Report

- **generated_at_utc**: 2026-06-07T17:55:46+00:00
- **dry_run**: True
- **ready_for_single_test_account_post**: True
- **published**: False
- **tweet_id**: 
- **tweet_url**: 
- **blocker**: 

## Gates

| Gate | Passed | Detail |
|------|--------|--------|
| publish_env | True | X_V2_009_PUBLISH_NOW=NOT_SET -> dry_run=True |
| x_api_credentials | False | missing=['X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET'] |
| selected_event_id | True | event_id=real_v006_rss_f12050b18970 is_meta_usdc=True |
| not_banned_event | True | banned_ids=['real_v006_rss_d30124a258e4'] |
| content_hash_not_previously_published | True | content_hash=37f9a0769fc02f3a previously_published=False |
| source_url_not_in_post | True | source_url_in_post=False |
| official_account | True | official_account=false |
| post_count_this_run | True | post_count_this_run=1 <= max=1 |

## Safety

- **official_account**: False
- **x_published**: False
- **x_api_connected**: False
- **post_count_this_run**: 1
- **daemon_started**: False
- **production_write**: False
- **article_project_modified**: False
- **credential_exposed**: False
