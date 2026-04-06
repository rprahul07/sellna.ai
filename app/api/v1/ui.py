"""UI configuration API.

This router exists to ensure the frontend contains **zero hardcoded datasets**
for displayed content (nav items, landing page feature lists, etc.).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/ui", tags=["UI Config"])


@router.get("/sidebar", summary="Sidebar navigation configuration")
async def get_sidebar_config() -> dict:
    return {
        "nav_items": [
            {"to": "/", "icon": "LayoutDashboard", "label": "Dashboard"},
            {"to": "/company", "icon": "Building2", "label": "Company Intel"},
            {"to": "/competitors", "icon": "Crosshair", "label": "Competitors"},
            {"to": "/icp", "icon": "Users", "label": "ICP Generator"},
            {"to": "/personas", "icon": "UserCircle", "label": "Personas"},
            {"to": "/outreach", "icon": "Send", "label": "Outreach"},
            {"to": "/analytics", "icon": "BarChart3", "label": "Analytics"},
        ]
    }


@router.get("/landing", summary="Landing page content configuration")
async def get_landing_config() -> dict:
    return {
        "hero_badge": "Now in Public Beta — Join 200+ teams",
        "hero_title_lines": ["Your AI-Powered", "Sales Intelligence", "Command Center"],
        "hero_subtitle": (
            "From company research to personalized outreach — automate your entire "
            "sales pipeline with autonomous AI agents that think, analyze, and act."
        ),
        "features": [
            {
                "icon": "Target",
                "title": "Competitor Intelligence",
                "desc": "Auto-discover and analyze competitors with AI-powered web scraping and gap analysis.",
            },
            {
                "icon": "Users",
                "title": "ICP & Persona Engine",
                "desc": "Generate ideal customer profiles and buyer personas backed by real market data.",
            },
            {
                "icon": "Sparkles",
                "title": "AI Outreach Generator",
                "desc": "Craft hyper-personalized emails, LinkedIn messages, and call scripts at scale.",
            },
            {
                "icon": "BarChart3",
                "title": "Performance Analytics",
                "desc": "Track open rates, replies, and conversions with real-time optimization feedback.",
            },
            {
                "icon": "Shield",
                "title": "Enterprise Security",
                "desc": "SOC 2 ready architecture with role-based access and encrypted data pipelines.",
            },
            {
                "icon": "Globe",
                "title": "Multi-Market Support",
                "desc": "Target across geographies with localized messaging and regional competitor mapping.",
            },
        ],
        "metrics": [
            {"value": "3.2x", "label": "Higher Reply Rates"},
            {"value": "67%", "label": "Faster Pipeline"},
            {"value": "10k+", "label": "Personas Generated"},
            {"value": "98%", "label": "Data Accuracy"},
        ],
        "workflow_steps": [
            "Enter your company details and product information",
            "AI agents analyze your domain and discover competitors",
            "Gap analysis identifies market opportunities",
            "ICPs and buyer personas are generated automatically",
            "Personalized outreach content is crafted for each persona",
        ],
        "hero_visual_labels": [
            "Domain Analysis",
            "Gap Detection",
            "ICP Generation",
            "Persona Engine",
            "Outreach AI",
            "Analytics",
        ],
        "app_name": "Sales Agentic AI",
        "footer_notice": "© 2026 Sales Agentic AI. All rights reserved.",
    }


@router.get("/company-input", summary="Company input page step configuration")
async def get_company_input_config() -> dict:
    return {
        "steps": [
            {"id": 1, "label": "Domain", "icon": "Globe"},
            {"id": 2, "label": "Company Details", "icon": "Building2"},
            {"id": 3, "label": "Product Intel", "icon": "Layers"},
            {"id": 4, "label": "Launch Pipeline", "icon": "Sparkles"},
        ],
        "what_happens_next": [
            {"icon": "Target", "label": "Domain analysis"},
            {"icon": "Users", "label": "Market mapping"},
            {"icon": "Sparkles", "label": "AI profiling"},
        ],
        "pipeline_agents": [
            "Domain Agent",
            "Competitor Agent",
            "Web Agent",
            "Cleaning Agent",
            "Gap Analysis",
            "ICP Agent",
            "Persona Agent",
            "Outreach Agent",
            "Optimization",
        ],
        "select_options": {
            "customer_type": [
                {"value": "B2B", "label": "B2B"},
                {"value": "B2C", "label": "B2C"},
                {"value": "B2B2C", "label": "B2B2C"},
                {"value": "Government", "label": "Government"},
                {"value": "Marketplace", "label": "Marketplace"},
            ],
            "pricing_model": [
                {"value": "freemium", "label": "Freemium"},
                {"value": "subscription", "label": "Subscription"},
                {"value": "usage_based", "label": "Usage Based"},
                {"value": "enterprise", "label": "Enterprise"},
                {"value": "one_time", "label": "One Time"},
                {"value": "other", "label": "Other"},
            ],
        },
        "defaults": {
            "industry": "B2B SaaS",
            "target_geography": "Global",
            "core_problem_solved": "General process inefficiency",
        },
    }


@router.get("/auth-copy", summary="Login/Signup marketing copy")
async def get_auth_copy() -> dict:
    return {
        "login_left": {
            "title": "AI-powered sales intelligence at your fingertips",
            "subtitle": (
                "Automate competitor analysis, generate ICPs, build personas, and craft personalized outreach — "
                "all powered by autonomous AI agents."
            ),
            "bullets": [
                "9 Autonomous AI Agents",
                "Real-time Gap Analysis",
                "Personalized Outreach at Scale",
            ],
        },
        "signup_left": {
            "title": "Start closing deals faster today",
            "subtitle": "Set up your workspace in under 2 minutes. No credit card required. Get instant access to all 9 AI agents.",
            "bullets": [
                "Unlimited competitor analysis",
                "AI-generated ICPs & personas",
                "Multi-channel outreach engine",
                "Real-time analytics dashboard",
            ],
        },
        "app_name": "Sales Agentic AI",
    }


@router.get("/personas", summary="Persona page section configuration")
async def get_personas_config() -> dict:
    return {
        "sections": [
            {"key": "goals", "label": "Goals", "icon": "Target", "color": "text-success", "bg": "bg-success/[0.06]"},
            {"key": "pain_points", "label": "Pain Points", "icon": "AlertTriangle", "color": "text-warning", "bg": "bg-warning/[0.06]"},
            {"key": "objections", "label": "Objections", "icon": "MessageSquare", "color": "text-destructive", "bg": "bg-destructive/[0.06]"},
            {"key": "buying_triggers", "label": "Buying Triggers", "icon": "Zap", "color": "text-primary", "bg": "bg-primary/[0.06]"},
        ]
    }

