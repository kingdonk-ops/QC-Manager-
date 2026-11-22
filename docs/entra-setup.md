# Microsoft Entra ID setup

Staff sign in with Entra ID. External users (clients, partners) use an email and password from an invitation, and never touch Entra.

The backend runs the whole OAuth flow as a confidential client: the browser only ever holds the app's own session cookie, never an Entra token.

## 1. App registration

Entra admin centre → **App registrations** → **New registration**

- **Supported account types**: *Accounts in this organizational directory only* (single tenant). The backend refuses tokens from any other tenant.
- **Redirect URI**: platform **Web**, `https://<app host>/api/v1/auth/oauth/callback/entra`. For local development add `http://localhost:5173/api/v1/auth/oauth/callback/entra`.

Then:

- **Certificates & secrets** → new client secret. Store it in your secret store, never in the repository.
- Note the **Directory (tenant) ID** and **Application (client) ID**.

Set `OAUTH_ENTRA_TENANT_ID`, `OAUTH_ENTRA_CLIENT_ID` and `OAUTH_ENTRA_CLIENT_SECRET`. Microsoft sign-in is enabled when all three are set.

## 2. App roles → roles

**App roles** → create one per role you want Entra to grant, for example:

| Display name | Value | Allowed member types |
|---|---|---|
| QC Administrator | `QC.Admin` | Users/Groups |
| QC Commercial | `QC.Commercial` | Users/Groups |
| QC Viewer | `QC.Viewer` | Users/Groups |

Assign users or groups to them under **Enterprise applications → <app> → Users and groups**. Turn on **Assignment required** on the same enterprise app, so only assigned people can sign in at all.

In the app, map each value to a role through `PUT /api/v1/entra/role-mappings/{value}` (needs `entra.manage`). `scripts/seed_demo.py` creates the three examples above. A mapped role is then held by exactly the users Entra assigns that app role to, refreshed at every sign-in. Roles with no mapping are assigned by hand.

## 3. Groups → teams

**Token configuration** → **Add groups claim** → choose **Groups assigned to the application** (recommended), or **Security groups**. ID token, Group ID format.

Create a team with that group's **Object ID** as `entra_group_id`. Its members then come from the group, at every sign-in through the `groups` claim, and hourly through Microsoft Graph. Who leads the team is still set in the app.

If a user is in more groups than fit in a token, Entra leaves the claim out; the sign-in then leaves their teams alone, and the hourly sync places them. "Groups assigned to the application" avoids that.

If you don't emit the groups claim at all, set `OAUTH_ENTRA_GROUPS_CLAIM=false` so a missing claim isn't read as "in no groups".

## 4. Graph sync (optional, recommended)

**API permissions** → Microsoft Graph → **Application permissions** → `GroupMember.Read.All` → **Grant admin consent**.

The worker then refreshes every linked team hourly (`team:sync_entra_groups`). Holders of `entra.manage` can run it now from the Teams page, or with `POST /api/v1/entra/sync`. It only reads from Entra.

## Behaviour to know

- An account that signed in with Entra can't use a password, even after a reset, so disabling the user in Entra, MFA and conditional access always apply.
- The first Entra sign-in links to an existing local account with the same email (the address comes from the tenant, so it's trusted).
- Signing out ends the app session, not the Microsoft one.
- The local superuser (`scripts/create_first_superuser.py`) signs in with a password. Keep it as a break-glass account with a strong secret.
