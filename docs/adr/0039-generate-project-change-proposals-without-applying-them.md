# Generate project change proposals without applying them

Status: accepted

The first writable extension of the Project Core Brain does not receive direct repository write authority. A separately authorized workflow creates one disposable isolated worktree at an explicit Git revision, generates the requested non-core document or feature, runs only its allowlisted verification, and returns a Project Change Proposal containing a patch, change summary, and test results.

The workflow cannot modify the active workspace, commit, switch the user's branch, push, or open a pull request. Applying a proposal requires an explicit process outside the Project Core Brain. Rejected or expired proposals permanently remove their isolated worktree and artifacts, and read-only project analysis never inherits these write permissions.
