# Unused Code Report

## definitely_unused_files

- None

## maybe_unused_files

- None

## unused_functions

- None

## unused_routes

- None

## unused_static_assets

- None

## runtime_data_files

- `Emotion-LLaMA/checkpoints/Llama-2-7b-chat-hf/model-00001-of-00002.safetensors`
- `Emotion-LLaMA/checkpoints/Llama-2-7b-chat-hf/model-00002-of-00002.safetensors`
- `Emotion-LLaMA/checkpoints/Llama-2-7b-chat-hf/pytorch_model-00001-of-00002.bin`
- `Emotion-LLaMA/checkpoints/Llama-2-7b-chat-hf/pytorch_model-00002-of-00002.bin`
- `Emotion-LLaMA/checkpoints/minigptv2_checkpoint.pth`
- `Emotion-LLaMA/checkpoints/save_checkpoint/Emoation_LLaMA.pth`
- `Emotion-LLaMA/checkpoints/transformer/chinese-hubert-large/chinese-hubert-large-fairseq-ckpt.pt`
- `Emotion-LLaMA/checkpoints/transformer/chinese-hubert-large/pytorch_model.bin`
- `UI_API/learning_data/emotion_order_media/pos_demo_001/1779710200388_84e881ef.webm`
- `UI_API/learning_data/emotion_order_media/pos_demo_001/index.json`
- `UI_API/learning_data/interaction_events.json`
- `UI_API/learning_data/intervention_logs.json`
- `UI_API/learning_data/rag_docs.json`
- `UI_API/learning_data/rag_vector_meta.json`
- `UI_API/learning_data/session_logs.json`
- `UI_API/learning_data/settings.json`

## safe_to_delete_static_assets

- None

## maybe_used_static_assets

- None

## keep_static_assets

- `UI_API/static/api.js`
- `UI_API/static/app.js`
- `UI_API/static/cart.js`
- `UI_API/static/mcd_categories/deals.jpg`
- `UI_API/static/mcd_categories/drinks.jpg`
- `UI_API/static/mcd_categories/kids.jpg`
- `UI_API/static/mcd_categories/recommended.jpg`
- `UI_API/static/mcd_categories/single.jpg`
- `UI_API/static/mcd_categories/value.jpg`
- `UI_API/static/mcd_start.png`
- `UI_API/static/media.js`
- `UI_API/static/media_buffer.js`
- `UI_API/static/menu_images/MCD001.jpg`
- `UI_API/static/menu_images/MCD002.jpg`
- `UI_API/static/menu_images/MCD003.jpg`
- `UI_API/static/menu_images/MCD004.jpg`
- `UI_API/static/menu_images/MCD005.jpg`
- `UI_API/static/menu_images/MCD006.jpg`
- `UI_API/static/menu_images/MCD007.jpg`
- `UI_API/static/menu_images/MCD008.jpg`
- `UI_API/static/menu_images/MCD009.jpg`
- `UI_API/static/menu_images/MCD010.jpg`
- `UI_API/static/menu_images/MCD011.jpg`
- `UI_API/static/menu_images/MCD012.jpg`
- `UI_API/static/menu_images/MCD013.jpg`
- `UI_API/static/menu_images/MCD014.jpg`
- `UI_API/static/menu_images/MCD015.jpg`
- `UI_API/static/menu_images/MCD016.jpg`
- `UI_API/static/menu_images/MCD017.jpg`
- `UI_API/static/menu_images/MCD018.jpg`
- `UI_API/static/menu_images/MCD019.jpg`
- `UI_API/static/menu_images/MCD020.jpg`
- `UI_API/static/menu_images/MCD021.jpg`
- `UI_API/static/menu_images/MCD022.jpg`
- `UI_API/static/menu_images/MCD023.jpg`
- `UI_API/static/menu_images/MCD024.jpg`
- `UI_API/static/menu_images/MCD025.jpg`
- `UI_API/static/menu_images/MCD026.jpg`
- `UI_API/static/menu_images/MCD027.jpg`
- `UI_API/static/menu_images/MCD028.jpg`
- `UI_API/static/menu_images/MCD029.jpg`
- `UI_API/static/menu_images/MCD030.jpg`
- `UI_API/static/menu_images/MCD031.jpg`
- `UI_API/static/menu_images/MCD032.jpg`
- `UI_API/static/realtime_client.js`
- `UI_API/static/recommendation.js`
- `UI_API/static/styles.css`
- `UI_API/static/ui.js`

## external_entrypoints_to_keep

- `/api/ask`
- `/api/auto_recommend`
- `/api/barrier_state`
- `/api/customer_service`
- `/api/debug/interaction_risk`
- `/api/debug/intervention_logs/{session_id}`
- `/api/interaction_event`
- `/api/intervention_result`
- `/api/rag_status`
- `/api/triggered_multimodal_analysis`
- `/demo-tool`
- `Emotion-LLaMA/app_EmotionLlamaClient.py`
- `UI_API/index.html`
- `UI_API/main.py`
- `UI_API/menu_data/menu.json`
- `tools/pos_interaction_demo_ui.py`

## frontend_split_plan

- {"phase": 1, "scope": "Do not split POS/Admin code in this cleanup pass; app.js still owns boot mode selection, shared state, and legacy-safe event wiring.", "title": "Keep current app.js runtime behavior"}
- {"phase": 2, "scope": "Move settings, logs, RAG admin, and statistics renderers behind a static/admin module after route/API smoke tests are stable.", "title": "Extract admin-only panels"}
- {"phase": 3, "scope": "Move POS event capture, risk trigger handling, media-buffer trigger calls, and checkout feedback into a static/pos_interaction module.", "title": "Extract POS interaction pipeline"}
- {"phase": 4, "scope": "Keep API wrapper, cart helpers, realtime client, media buffer, and UI primitives as shared modules; avoid moving business decisions into frontend.", "title": "Keep shared utilities small"}
