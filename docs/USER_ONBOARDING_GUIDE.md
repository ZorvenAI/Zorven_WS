# AI Brand Automator — User Onboarding Guide

> Welcome to AI Brand Automator! This guide explains how workspaces, teams, and permissions work so you can get started quickly.

---

## Table of Contents

1. [What is a Workspace?](#1-what-is-a-workspace)
2. [User Roles Explained](#2-user-roles-explained)
3. [Getting Started by Role](#3-getting-started-by-role)
   - [Brand Owner / Consultant](#31-brand-owner--consultant)
   - [Admin (Agency Manager)](#32-admin-agency-manager)
   - [Editor (Content Creator)](#33-editor-content-creator)
   - [Viewer (Client Stakeholder)](#34-viewer-client-stakeholder)
4. [Managing Multiple Brands](#4-managing-multiple-brands)
5. [Team Management](#5-team-management)
6. [Permissions Reference](#6-permissions-reference)
7. [Common Scenarios](#7-common-scenarios)
8. [FAQ](#8-faq)

---

## 1. What is a Workspace?

A **workspace** is a private, isolated environment for a single brand. Everything related to that brand lives inside its workspace:

- Company profile and brand strategy
- Uploaded brand assets (logos, images, documents)
- AI chat sessions and generated content
- Social media accounts and content calendar
- Subscription and billing

**Each brand = one workspace.** Data in one workspace is completely invisible from another. A social media post scheduled in the "Bransol" workspace cannot be seen from the "FreshBake" workspace, even by the same user.

```
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  Workspace: Bransol          │    │  Workspace: FreshBake        │
│  ───────────────────────     │    │  ───────────────────────     │
│  Company: Bransol LLC        │    │  Company: FreshBake Bakery   │
│  Assets: 23 files            │    │  Assets: 8 files             │
│  AI Sessions: 5              │    │  AI Sessions: 2              │
│  Social: LinkedIn, Twitter   │    │  Social: Instagram, Facebook │
│  Plan: Pro ($79/mo)          │    │  Plan: Basic ($29/mo)        │
└──────────────────────────────┘    └──────────────────────────────┘
        Completely separate — no shared data
```

---

## 2. User Roles Explained

Every user in a workspace has a **role** that determines what they can do. There are four roles, from most access to least:

### Owner

The person who created the workspace. Full control over everything.

- **Who it's for**: Brand founders, solo consultants, agency principals
- **What they can do**: Everything — including billing, deleting the workspace, and managing all team members
- **Limit**: Every workspace must have at least one Owner. The last Owner cannot be removed.

### Admin

A trusted manager who can run the workspace day-to-day.

- **Who it's for**: Agency managers, senior strategists, project leads
- **What they can do**: Everything an Owner can do, **except** managing billing and deleting the workspace
- **Typical use**: An agency Owner adds their project manager as Admin so they can invite freelancers and manage brand settings without needing Owner access to billing

### Editor

A hands-on team member who creates and manages content.

- **Who it's for**: Content creators, graphic designers, social media managers, copywriters
- **What they can do**: Upload assets, use AI tools, create and schedule social media posts, manage the content calendar
- **What they can't do**: Invite or remove team members, change brand settings, connect social accounts, access billing

### Viewer

A read-only observer who can see everything but change nothing.

- **Who it's for**: Clients reviewing progress, external stakeholders, executives who want visibility
- **What they can do**: View the dashboard, browse assets, read AI chat history, review the content calendar
- **What they can't do**: Upload, edit, delete, schedule, or change anything

---

## 3. Getting Started by Role

### 3.1 Brand Owner / Consultant

You're building a brand — either your own or for a client.

**Step 1: Create your account**

Sign up at the registration page. Enter your name, email, password, and your **brand name** (e.g., "Bransol" or "FreshBake Bakery").

```
┌──────────────────────────────┐
│  Create Your Account         │
│                              │
│  First Name:  [Naveen     ]  │
│  Last Name:   [Hanuman    ]  │
│  Email:       [naveen@... ]  │
│  Password:    [••••••••   ]  │
│  Brand Name:  [Bransol    ]  │  ← Your first workspace
│                              │
│  [Create Account]            │
└──────────────────────────────┘
```

This creates your account **and** your first workspace. You are the **Owner**.

**Step 2: Complete onboarding**

You'll be guided through the onboarding wizard:
1. Enter company information (industry, target audience, core problem)
2. AI generates your brand strategy (vision, mission, values)
3. AI generates your brand identity (colors, fonts, messaging)
4. Upload brand assets (logos, images, documents)
5. Review and finalize

**Step 3: Start using the platform**

- Use the **AI Chat** to refine your brand strategy
- Connect **social media accounts** (LinkedIn, Twitter, Instagram, Facebook)
- Create and schedule posts via the **Content Calendar**
- Invite team members (see [Team Management](#5-team-management))

**Step 4: Add more brands** (if you're a consultant)

See [Managing Multiple Brands](#4-managing-multiple-brands).

---

### 3.2 Admin (Agency Manager)

You've been invited by an Owner to help manage a brand workspace.

**Step 1: Accept your invitation**

You'll receive an email with an invitation link. Click it to create your account (or log in if you already have one).

```
┌──────────────────────────────────────────────┐
│  You've been invited!                        │
│                                              │
│  Naveen Hanuman has invited you to join      │
│  "Bransol" as an Admin.                      │
│                                              │
│  [Accept Invitation]                         │
└──────────────────────────────────────────────┘
```

**Step 2: You're in**

After accepting, the workspace appears in your workspace switcher. You can:

- Edit the company profile and brand settings
- Connect and manage social media accounts
- Invite Editors and Viewers to the team
- Use AI tools and manage the content calendar

**What you can't do as Admin:**
- Change the subscription plan or access billing
- Delete the workspace
- Remove or demote the Owner

---

### 3.3 Editor (Content Creator)

You've been invited to create content for a brand.

**Step 1: Accept your invitation**

Same as Admin — click the invitation link, create your account or log in.

**Step 2: Start creating**

You'll land on the brand's dashboard. You can:

- Upload brand assets (images, documents, videos)
- Use the **AI Chat** to brainstorm ideas and generate content
- Generate brand strategies and market analyses
- Create social media posts and add them to the **Content Calendar**
- Schedule posts for auto-publishing

**What you can't do as Editor:**
- Invite or remove team members
- Change company settings or brand voice
- Connect or disconnect social media accounts
- Access billing or subscription settings

**Example: A typical Editor workflow**

```
1. Open the workspace → Dashboard shows brand overview
2. Go to AI Chat → "Generate 5 LinkedIn post ideas for our product launch"
3. AI generates ideas → pick your favorite
4. Go to Content Calendar → Create new post with the AI-generated content
5. Attach a brand asset (image) → Schedule for next Tuesday at 9 AM
6. Done — the post will auto-publish
```

---

### 3.4 Viewer (Client Stakeholder)

You've been given read-only access to review a brand's progress.

**Step 1: Accept your invitation**

Click the invitation link and create your account.

**Step 2: Browse and review**

You'll see the brand's dashboard with full visibility:

- **Dashboard**: Overview of brand status, recent activity
- **Brand Assets**: Browse all uploaded files (logos, images, documents)
- **AI History**: Read past AI chat sessions and generated strategies
- **Content Calendar**: See all scheduled and published posts
- **Analytics**: View engagement metrics (when available)

**What you can't do as Viewer:**
- Upload, edit, or delete anything
- Use AI generation tools
- Create or modify social media posts
- Manage team members or settings
- Access billing

**This role is perfect for:**
- A bakery owner who hired a consultant — log in to see what content is planned for the week
- A CEO who wants to check brand progress without accidentally changing anything
- An external stakeholder reviewing deliverables

---

## 4. Managing Multiple Brands

If you're a consultant or agency managing several brands, each brand gets its own workspace.

### Creating Additional Brands

Click the **workspace switcher** (top of the sidebar) and select **"+ Create New Brand"**:

```
┌─────────────────────────┐
│ 🏢 Bransol          ▼  │  ← currently active
├─────────────────────────┤
│ ✓ Bransol    (Owner)    │
│   FreshBake  (Owner)    │
│   TechNova   (Owner)    │
│   ─────────────────     │
│   + Create New Brand    │  ← click here
└─────────────────────────┘
```

Enter the new brand name, and you'll have a fresh workspace ready for onboarding.

### Switching Between Brands

Click the workspace switcher and select the brand you want to work on. The dashboard, assets, AI history, and content calendar all update instantly to show that brand's data.

```
Working on Bransol...     →  Click "FreshBake"  →  Now seeing FreshBake data
X-Tenant-ID: 24                                    X-Tenant-ID: 31
```

**Important**: Each workspace is completely isolated. An asset uploaded to Bransol does not appear in FreshBake. A social post scheduled in FreshBake does not appear in Bransol.

### Example: Consultant with Three Clients

```
Naveen's Workspaces:
──────────────────────────────────────────────────────────
Bransol (Owner)
  ├── Team: Naveen (Owner), Raj (Editor)
  ├── Assets: 23 files
  ├── Social: LinkedIn, Twitter connected
  └── Plan: Pro ($79/mo)

FreshBake (Owner)
  ├── Team: Naveen (Owner), Raj (Editor), Priya (Editor), Bob (Viewer)
  ├── Assets: 8 files
  ├── Social: Instagram, Facebook connected
  └── Plan: Basic ($29/mo)

TechNova (Owner)
  ├── Team: Naveen (Owner)
  ├── Assets: 12 files
  ├── Social: LinkedIn connected
  └── Plan: Pro ($79/mo)
```

Each brand has its own subscription, its own team, and its own data. Naveen manages all three. Raj works on two. Priya and Bob only see FreshBake.

---

## 5. Team Management

### Inviting Team Members

Owners and Admins can invite people to the workspace.

1. Go to **Settings → Team** (or the Team page in the sidebar)
2. Click **"Invite Member"**
3. Enter their email address and select a role

```
┌─────────────────────────────────────┐
│  Invite Team Member                 │
│                                     │
│  Email:  [priya@design.co       ]   │
│  Role:   [Editor            ▼   ]   │
│           ┌─────────────────┐       │
│           │ Admin           │       │
│           │ Editor      ✓   │       │
│           │ Viewer          │       │
│           └─────────────────┘       │
│                                     │
│  [Send Invitation]                  │
└─────────────────────────────────────┘
```

**What happens:**
- If they already have an account → the workspace appears in their switcher on next login
- If they're new → they receive an email with a registration link. After signing up, the workspace is automatically added

### Changing a Member's Role

From the Team page, click the settings icon next to a member and select a new role.

```
┌─────────────────────────────────────────────────┐
│  Team Members                          [Invite] │
├─────────────────────────────────────────────────┤
│  naveen@gmail.com      Owner                    │
│  priya@design.co       Editor     [⚙️]  [✕]    │
│  bob@freshbake.com     Viewer     [⚙️]  [✕]    │
└─────────────────────────────────────────────────┘
```

**Rules:**
- Owners and Admins can change roles of Editors and Viewers
- Only Owners can promote someone to Admin
- The last Owner cannot be demoted or removed
- You cannot change your own role

### Removing a Member

Click the **✕** next to their name. They will immediately lose access to the workspace. Their data (posts they created, assets they uploaded) remains in the workspace.

---

## 6. Permissions Reference

### Quick Reference Table

| Action | Owner | Admin | Editor | Viewer |
|--------|:-----:|:-----:|:------:|:------:|
| **View & Browse** | | | | |
| View dashboard and analytics | ✅ | ✅ | ✅ | ✅ |
| Browse brand assets | ✅ | ✅ | ✅ | ✅ |
| Read AI chat history | ✅ | ✅ | ✅ | ✅ |
| View content calendar | ✅ | ✅ | ✅ | ✅ |
| View team members list | ✅ | ✅ | ✅ | ✅ |
| **Create & Edit** | | | | |
| Upload brand assets | ✅ | ✅ | ✅ | ❌ |
| Delete brand assets | ✅ | ✅ | ✅ | ❌ |
| Use AI chat and generation | ✅ | ✅ | ✅ | ❌ |
| Create/edit social media posts | ✅ | ✅ | ✅ | ❌ |
| Schedule/publish posts | ✅ | ✅ | ✅ | ❌ |
| **Manage** | | | | |
| Edit company profile and settings | ✅ | ✅ | ❌ | ❌ |
| Connect/disconnect social accounts | ✅ | ✅ | ❌ | ❌ |
| Invite and remove team members | ✅ | ✅ | ❌ | ❌ |
| Change member roles | ✅ | ✅ | ❌ | ❌ |
| **Owner-Only** | | | | |
| Manage subscription and billing | ✅ | ❌ | ❌ | ❌ |
| Delete the workspace | ✅ | ❌ | ❌ | ❌ |
| Promote members to Admin | ✅ | ❌ | ❌ | ❌ |

### What Happens When You Try Something You Can't Do?

- **In the UI**: Buttons and options you don't have permission for won't be visible. For example, Viewers don't see the "Upload" button, and Editors don't see the "Team" settings page.
- **Via API**: If you try to perform an action you're not authorized for, you'll receive a **403 Forbidden** error with a clear message.

---

## 7. Common Scenarios

### Scenario 1: Solo Brand Owner

**Sarah** runs a small business and handles everything herself.

- She signs up and creates workspace "Sarah's Boutique"
- She's the only user (Owner)
- She uploads assets, uses AI, schedules posts — no team needed
- If she later hires a social media manager, she can invite them as Editor

### Scenario 2: Brand Consultant with Multiple Clients

**Naveen** is a branding consultant with three clients.

- He creates three workspaces: Bransol, FreshBake, TechNova
- He's Owner of all three
- He hires **Raj** (social media) and invites him as Editor on Bransol and FreshBake
- He hires **Priya** (design) and invites her as Editor on FreshBake only
- He gives **Bob** (FreshBake's bakery owner) Viewer access to FreshBake

```
Naveen's view:  3 workspaces in switcher
Raj's view:     2 workspaces (Bransol, FreshBake)
Priya's view:   1 workspace (FreshBake)
Bob's view:     1 workspace (FreshBake, read-only)
```

### Scenario 3: Marketing Agency

**CreativeMinds Agency** manages brands for 10 clients.

- **Agency Owner (CEO)** creates all 10 workspaces — Owner of each
- **Account Manager** is added as Admin on their 3 assigned clients — can manage teams and settings
- **Content Writers** are added as Editors on specific brands — create content, use AI, schedule posts
- **Each Client** gets Viewer access to their own brand — can review progress but not change anything

### Scenario 4: Team Growing Over Time

**Week 1**: Sara creates "GreenLeaf" workspace. She's alone, does everything.

**Week 4**: Sara hires a content writer, Alex. She invites Alex as **Editor**.
- Alex can upload assets, use AI chat, schedule posts
- Alex can't change brand settings or connect social accounts

**Week 8**: Sara hires a project manager, Maria. She invites Maria as **Admin**.
- Maria can now invite more Editors, manage social accounts, edit brand settings
- Maria can't touch billing — only Sara can

**Week 12**: Sara gives her investor, James, **Viewer** access.
- James logs in monthly to review the content calendar and brand progress
- James can't change anything

### Scenario 5: Freelancer Working for Multiple Agencies

**Priya** is a freelance designer. Two different agencies invite her:

- **CreativeMinds Agency** invites Priya as Editor on "FreshBake"
- **BrandBuilders Inc** invites Priya as Editor on "TechStyle"

Priya logs in and sees both workspaces in her switcher. She switches between them as needed. The two agencies don't know about each other — their workspaces are completely separate.

```
Priya's workspace switcher:
┌─────────────────────────┐
│ 🏢 FreshBake        ▼  │
├─────────────────────────┤
│ ✓ FreshBake  (Editor)   │  ← from CreativeMinds
│   TechStyle  (Editor)   │  ← from BrandBuilders
└─────────────────────────┘
```

---

## 8. FAQ

### Account & Access

**Q: Can I belong to multiple workspaces?**
Yes. You have one account and can be a member of as many workspaces as you're invited to (or create).

**Q: Can I have different roles in different workspaces?**
Yes. You might be an Owner of your own brand and an Editor in a client's workspace. Your role is per-workspace, not global.

**Q: What happens if I'm removed from a workspace?**
You immediately lose access. The workspace disappears from your switcher. Content you created (posts, uploads) stays in the workspace.

**Q: Can I leave a workspace on my own?**
Yes, unless you're the last Owner. The last Owner must transfer ownership before leaving.

### Workspaces & Data

**Q: Is data shared between workspaces?**
No. Each workspace is completely isolated. Assets, AI history, social accounts, and the content calendar are all workspace-specific.

**Q: Can I move data from one workspace to another?**
Not currently. Each workspace is independent. You would need to re-upload assets or re-create content in the other workspace.

**Q: Does each workspace need its own subscription?**
Yes. Each workspace (brand) has its own subscription plan (Basic $29/mo, Pro $79/mo, or Enterprise $199/mo). The Owner manages billing for each workspace.

**Q: What happens if a subscription expires?**
The workspace enters a read-only state. All data is preserved, but you can't create new content, upload assets, or use AI tools until the subscription is renewed.

### Team & Permissions

**Q: Can an Editor invite other people?**
No. Only Owners and Admins can invite or remove team members.

**Q: Can I see who's in a workspace if I'm a Viewer?**
Yes. All members can see the team list. But only Owners and Admins can make changes.

**Q: What's the difference between Admin and Owner?**
Admins can do almost everything — manage the team, edit settings, connect social accounts. The key differences: only Owners can manage billing, delete the workspace, and promote members to Admin.

**Q: Can there be multiple Owners?**
Yes. An Owner can promote an Admin to Owner. This is useful for co-founders or partners who share equal control.

**Q: What if I forget which workspace I'm in?**
The workspace name is always visible at the top of the sidebar in the workspace switcher. Everything on screen belongs to that workspace.

---

## Quick Start Checklist

### If you're a Brand Owner:
- [ ] Create your account with your brand name
- [ ] Complete the onboarding wizard (company info → brand strategy → identity → assets)
- [ ] Connect your social media accounts
- [ ] Invite your team members
- [ ] Start creating and scheduling content

### If you're an Admin:
- [ ] Accept your invitation (check email)
- [ ] Review the brand profile and settings
- [ ] Invite Editors and Viewers as needed
- [ ] Connect any remaining social accounts

### If you're an Editor:
- [ ] Accept your invitation (check email)
- [ ] Browse existing brand assets to get familiar
- [ ] Start an AI chat to brainstorm content ideas
- [ ] Create your first social media post

### If you're a Viewer:
- [ ] Accept your invitation (check email)
- [ ] Browse the dashboard for a brand overview
- [ ] Check the content calendar to see what's planned
- [ ] Review brand assets and AI-generated strategies

---

*Need help? Contact support at support@brandautomator.com*
