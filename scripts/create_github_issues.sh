#!/bin/bash

# Script to create GitHub issues for AI Brand Automator codebase fixes
# Generated from CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md

echo "Creating GitHub Issues for AI Brand Automator..."

# CRITICAL ISSUES (4)

gh issue create \
  --title "🔴 [CRITICAL] Multi-tenancy middleware enabled but broken" \
  --label "critical,bug,backend,multi-tenancy" \
  --body "## Issue C-01

**Location**: \`brand_automator/settings.py\` Line 73

**Problem**: \`django_tenants.middleware.main.TenantMainMiddleware\` is in MIDDLEWARE list but tenant system is disabled. Every request tries to resolve \`request.tenant\` and fails with AttributeError.

**Impact**: ALL API requests fail

**Evidence**: 23+ references to \`request.tenant\` across views

**Root Cause**: Inconsistent configuration - middleware is active but tenant models commented out

## Fix Required

**Option B Selected**: Fully enable multi-tenancy (per user approval)

### Implementation Steps:
1. Enable tenant models in SHARED_APPS and TENANT_APPS
2. Configure DATABASE_ROUTERS
3. Set TENANT_MODEL and TENANT_DOMAIN_MODEL
4. Create domain routing logic
5. Test: All API requests resolve tenant correctly

### Code Changes Needed:
\`\`\`python
# settings.py
SHARED_APPS = [
    'django_tenants',  # Must be first
    'tenants',
    'django.contrib.contenttypes',
    'django.contrib.auth',
]

TENANT_APPS = [
    'onboarding',
    'ai_services',
    'files',
]

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)
TENANT_MODEL = \"tenants.Tenant\"
TENANT_DOMAIN_MODEL = \"tenants.Domain\"
\`\`\`

**Priority**: BLOCKING - Must be fixed before any other work
**Estimated Time**: 8-12 hours
**Dependencies**: None
**Blocks**: C-02, C-04, H-01, H-05, H-08, H-09

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#c-01-multi-tenancy-middleware-enabled-but-broken)"

echo "Created issue C-01: Multi-tenancy"

gh issue create \
  --title "🔴 [CRITICAL] No user registration endpoint" \
  --label "critical,feature,backend,authentication" \
  --body "## Issue C-02

**Location**: \`brand_automator/urls.py\`

**Missing**: \`POST /api/v1/auth/register/\`

**Impact**: Users cannot create accounts

**Frontend Reference**: \`RegisterForm.tsx\` Line 30 shows message: \"Registration is not implemented yet\"

## Fix Required

### Implementation Steps:
1. Create \`UserRegistrationSerializer\` with validation
2. Create \`UserRegistrationView\` 
3. Add URL route for \`/api/v1/auth/register/\`
4. Create tenant schema for new user (Option B)
5. Create default domain for tenant
6. Generate JWT tokens
7. Test: Can register user and receive tokens

### Code Changes Needed:
\`\`\`python
# auth/serializers.py
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    email = serializers.EmailField(required=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password']
    
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        
        # Create tenant schema for user
        tenant = Tenant.objects.create(
            schema_name=f'tenant_{user.id}',
            name=f\"{user.username}'s Company\"
        )
        
        # Create domain
        Domain.objects.create(
            domain=f'{user.username}.localhost',
            tenant=tenant,
            is_primary=True
        )
        
        return user

# auth/views.py
class UserRegistrationView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'tenant_domain': f'{user.username}.localhost'
            }, status=201)
        return Response(serializer.errors, status=400)
\`\`\`

**Priority**: BLOCKING - Required for user signup
**Estimated Time**: 4-6 hours
**Dependencies**: C-01 (multi-tenancy must be working)
**Blocks**: All user workflows

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#c-02-no-user-registration-endpoint)"

echo "Created issue C-02: User registration"

gh issue create \
  --title "🔴 [CRITICAL] JWT login email/username mismatch" \
  --label "critical,bug,backend,frontend,authentication" \
  --body "## Issue C-03

**Location**: JWT authentication + \`LoginForm.tsx\`

**Problem**: 
- Django User model expects \`username\` field
- simplejwt expects \`username\` in login request
- Frontend sends \`email\` in login request

**Frontend Code**: \`LoginForm.tsx\` Line 17:
\`\`\`typescript
const formData = { email: '', password: '' }
\`\`\`

**Impact**: All login attempts return 400 Bad Request

## Fix Required

### Option 1: Custom JWT Serializer (Recommended)
\`\`\`python
# auth/serializers.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'
    
    def validate(self, attrs):
        # Find user by email
        email = attrs.get('email')
        password = attrs.get('password')
        
        try:
            user = User.objects.get(email=email)
            user = authenticate(username=user.username, password=password)
            if user is None:
                raise AuthenticationFailed('Invalid credentials')
        except User.DoesNotExist:
            raise AuthenticationFailed('Invalid credentials')
        
        refresh = self.get_token(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

# urls.py
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import EmailTokenObtainPairSerializer

class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer

urlpatterns = [
    path('api/v1/auth/login/', EmailTokenObtainPairView.as_view()),
]
\`\`\`

### Option 2: Frontend sends username
Not recommended - UX is worse (users expect email login)

**Priority**: BLOCKING - Login doesn't work
**Estimated Time**: 2-3 hours
**Dependencies**: None
**Blocks**: All authenticated workflows

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#c-03-jwt-login-emailusername-mismatch)"

echo "Created issue C-03: JWT login"

gh issue create \
  --title "🔴 [CRITICAL] No tenant creation workflow" \
  --label "critical,feature,backend,multi-tenancy" \
  --body "## Issue C-04

**Location**: Throughout onboarding flow

**Problem**: No mechanism to create \`Tenant\` records for new users. When company creation is attempted, it fails due to missing \`tenant\` foreign key.

**Evidence**: \`onboarding/views.py\` Line 36 tries to save Company without tenant

**Impact**: Company creation fails with foreign key constraint violation

## Fix Required

### Implementation Steps:
1. Tenant creation should happen during user registration (see C-02)
2. Update CompanyViewSet to use \`request.tenant\`
3. Update all views to filter by tenant
4. Test: Company saves with tenant association

### Code Changes Needed:
\`\`\`python
# onboarding/views.py
class CompanyViewSet(viewsets.ModelViewSet):
    serializer_class = CompanyCreateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Filter companies by current tenant
        return Company.objects.filter(tenant=self.request.tenant)
    
    def perform_create(self, serializer):
        # Save company with current tenant
        company = serializer.save(tenant=self.request.tenant)
        
        # Create onboarding progress
        OnboardingProgress.objects.create(
            tenant=self.request.tenant,
            company=company,
            current_step='company_info',
            steps_completed=[]
        )
\`\`\`

**Priority**: BLOCKING - Company creation doesn't work
**Estimated Time**: 3-4 hours
**Dependencies**: C-01 (multi-tenancy working), C-02 (tenant created on registration)
**Blocks**: All onboarding workflows

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#c-04-no-tenant-creation-workflow)"

echo "Created issue C-04: Tenant creation workflow"

# HIGH PRIORITY ISSUES (20)

gh issue create \
  --title "🟠 [HIGH] Foreign key constraint violations on tenant fields" \
  --label "high,bug,backend,database,multi-tenancy" \
  --body "## Issue H-01

**Locations**:
- \`onboarding/models.py\` Line 7: \`Company.tenant = OneToOneField(Tenant)\`
- \`onboarding/models.py\` Line 39: \`BrandAsset.tenant = ForeignKey(Tenant)\`
- \`ai_services/models.py\` Line 7: \`ChatSession.tenant = ForeignKey(Tenant)\`

**Problem**: All models reference \`Tenant\`, but with multi-tenancy partially disabled, these foreign keys fail

**Impact**: 
- Model saves fail with constraint violations
- Migrations may fail if tenant records don't exist

## Fix Required

Once multi-tenancy is fully enabled (C-01), ensure:
1. All migrations run successfully
2. Tenant foreign keys are properly set on create
3. All queries filter by tenant
4. No cross-tenant data leaks

### Test Cases Needed:
\`\`\`python
@pytest.mark.django_db
def test_company_requires_tenant():
    with pytest.raises(IntegrityError):
        Company.objects.create(name='Test', tenant=None)

@pytest.mark.django_db
def test_company_isolated_by_tenant(tenant1, tenant2):
    with schema_context(tenant1.schema_name):
        company1 = Company.objects.create(name='Company 1', tenant=tenant1)
    
    with schema_context(tenant2.schema_name):
        companies = Company.objects.all()
        assert company1 not in companies
\`\`\`

**Priority**: HIGH - Data integrity issue
**Estimated Time**: 2-3 hours (testing + validation)
**Dependencies**: C-01 (multi-tenancy enabled)

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-01-foreign-key-constraint-violations)"

echo "Created issue H-01: Foreign key constraints"

gh issue create \
  --title "🟠 [HIGH] Database credentials exposed in source code" \
  --label "high,security,backend,configuration" \
  --body "## Issue H-02

**Location**: \`settings.py\` Lines 103-109

**Problem**: Hardcoded Neon PostgreSQL credentials in source code

\`\`\`python
'PASSWORD': '<REDACTED>',  # ⚠️ EXPOSED!
'HOST': '<REDACTED>.us-east-2.aws.neon.tech',
\`\`\`

**Risk**: 
- Credentials committed to Git repository
- Anyone with repo access can access database
- Credentials visible in Git history

## Fix Required

### Implementation Steps:
1. Create \`.env\` file (add to .gitignore)
2. Move all sensitive data to environment variables
3. Create \`.env.example\` template
4. **Rotate database password immediately**
5. Update documentation

### Code Changes:
\`\`\`python
# settings.py
from decouple import config

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': config('DATABASE_NAME'),
        'USER': config('DATABASE_USER'),
        'PASSWORD': config('DATABASE_PASSWORD'),
        'HOST': config('DATABASE_HOST'),
        'PORT': config('DATABASE_PORT', default='5432'),
    }
}
\`\`\`

\`\`\`bash
# .env.example
DATABASE_NAME=ai_brand_automator
DATABASE_USER=your_user
DATABASE_PASSWORD=your_password
DATABASE_HOST=your_host.neon.tech
DATABASE_PORT=5432
\`\`\`

**IMMEDIATE ACTION REQUIRED**: 
1. Rotate the exposed password in Neon console
2. Update production deployment with new credentials
3. Never commit .env file

**Priority**: HIGH - Security vulnerability
**Estimated Time**: 1 hour
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-02-database-credentials-exposed)"

echo "Created issue H-02: Database credentials"

gh issue create \
  --title "🟠 [HIGH] SECRET_KEY exposed with insecure default" \
  --label "high,security,backend,configuration" \
  --body "## Issue H-03

**Location**: \`settings.py\` Line 24

**Problem**: DEFAULT fallback key is insecure Django development key

**Risk**: Production use would be vulnerable to session hijacking and CSRF attacks

## Fix Required

\`\`\`python
# settings.py
SECRET_KEY = config('SECRET_KEY')  # No default!

# In .env
SECRET_KEY=<generate-secure-random-key>
\`\`\`

Generate new secret key:
\`\`\`bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
\`\`\`

**Priority**: HIGH - Security vulnerability
**Estimated Time**: 15 minutes
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-03-secret_key-exposed)"

echo "Created issue H-03: SECRET_KEY"

gh issue create \
  --title "🟠 [HIGH] File upload endpoint has hardcoded company ID" \
  --label "high,bug,backend,files" \
  --body "## Issue H-04

**Location**: \`onboarding/views.py\` Lines 124-126

\`\`\`python
company = get_object_or_404(Company, pk=1)  # ⚠️ Hardcoded ID!
\`\`\`

**Problems**:
1. Assumes company with ID=1 exists
2. No tenant filtering
3. GCS upload commented out (Line 130)
4. Any authenticated user uploads to company ID 1

## Fix Required

\`\`\`python
@action(detail=True, methods=['post'])
def upload_asset(self, request, pk=None):
    company = self.get_object()  # Uses pk from URL
    
    serializer = BrandAssetSerializer(data=request.data)
    if serializer.is_valid():
        # Upload to GCS
        file_obj = request.FILES.get('file')
        file_url = upload_to_gcs(file_obj, request.tenant.schema_name)
        
        # Save asset
        asset = serializer.save(
            company=company,
            tenant=request.tenant,
            file_url=file_url
        )
        return Response(BrandAssetSerializer(asset).data)
    return Response(serializer.errors, status=400)
\`\`\`

**Priority**: HIGH - Data integrity issue
**Estimated Time**: 2-3 hours
**Dependencies**: C-01 (multi-tenancy), H-06 (GCS config)

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-04-file-upload-endpoint-broken)"

echo "Created issue H-04: File upload"

gh issue create \
  --title "🟠 [HIGH] AI service tenant logging fails" \
  --label "high,bug,backend,ai-services" \
  --body "## Issue H-05

**Location**: \`ai_services/services.py\` Line 76

\`\`\`python
AIGeneration.objects.create(
    tenant=company_data.get('tenant'),  # This is object, not validated
    # ...
)
\`\`\`

**Problem**: \`company_data.get('tenant')\` returns \`request.tenant\` object or None, causing foreign key constraint violation

## Fix Required

\`\`\`python
# ai_services/services.py
def generate_brand_strategy(self, company_data: dict, tenant=None) -> dict:
    # ... generation logic ...
    
    # Log generation with proper tenant
    AIGeneration.objects.create(
        tenant=tenant,  # Pass tenant explicitly
        generation_type='brand_strategy',
        prompt=prompt,
        response=result_text,
        tokens_used=token_count,
        processing_time=processing_time
    )
    
    return result

# In views.py
@action(detail=True, methods=['post'])
def generate_brand_strategy(self, request, pk=None):
    company = self.get_object()
    result = ai_service.generate_brand_strategy(
        company_data,
        tenant=request.tenant  # Pass tenant explicitly
    )
\`\`\`

**Priority**: HIGH - AI logging doesn't work
**Estimated Time**: 1-2 hours
**Dependencies**: C-01 (multi-tenancy)

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-05-ai-service-tenant-logging-failure)"

echo "Created issue H-05: AI service logging"

gh issue create \
  --title "🟠 [HIGH] Missing GCS configuration" \
  --label "high,feature,backend,files,configuration" \
  --body "## Issue H-06

**Location**: \`brand_automator/settings.py\` Lines 197-199

**Problem**: All GCS settings default to empty strings

\`\`\`python
GS_BUCKET_NAME = config('GS_BUCKET_NAME', default='')
GS_PROJECT_ID = config('GS_PROJECT_ID', default='')
GS_CREDENTIALS = config('GS_CREDENTIALS_PATH', default='')
\`\`\`

**Impact**: File uploads return mock URLs instead of real storage

## Fix Required

### Setup Steps:
1. Create GCS bucket in Google Cloud Console
2. Create service account with Storage Admin role
3. Download JSON credentials
4. Configure environment variables

\`\`\`bash
# .env
GS_BUCKET_NAME=ai-brand-automator-assets
GS_PROJECT_ID=your-project-id
GS_CREDENTIALS_PATH=/path/to/service-account-key.json
\`\`\`

\`\`\`python
# files/services.py
from google.cloud import storage
from decouple import config

def upload_to_gcs(file_obj, tenant_schema: str) -> str:
    \"\"\"Upload file to Google Cloud Storage\"\"\"
    if not config('GS_BUCKET_NAME'):
        raise ValueError('GCS not configured')
    
    client = storage.Client()
    bucket = client.bucket(config('GS_BUCKET_NAME'))
    
    # Organize by tenant
    blob_name = f'{tenant_schema}/{file_obj.name}'
    blob = bucket.blob(blob_name)
    
    blob.upload_from_file(file_obj)
    
    return blob.public_url
\`\`\`

**Priority**: HIGH - File storage doesn't work
**Estimated Time**: 3-4 hours (setup + implementation)
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-06-missing-gcs-configuration)"

echo "Created issue H-06: GCS configuration"

gh issue create \
  --title "🟠 [HIGH] Missing authentication decorators on API views" \
  --label "high,security,backend" \
  --body "## Issue H-07

**Location**: \`ai_services/views.py\` Lines 46, 97, 137, 177

**Problem**: \`@api_view(['POST'])\` decorators don't enforce authentication

**Impact**: Unauthenticated users can access AI services, costing money and exposing data

## Fix Required

\`\`\`python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

@api_view(['POST'])
@permission_classes([IsAuthenticated])  # Add this!
def generate_brand_strategy(request):
    # ...

@api_view(['POST'])
@permission_classes([IsAuthenticated])  # Add this!
def generate_brand_identity(request):
    # ...

@api_view(['POST'])
@permission_classes([IsAuthenticated])  # Add this!
def chat_endpoint(request):
    # ...
\`\`\`

**Priority**: HIGH - Security vulnerability
**Estimated Time**: 30 minutes
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-07-missing-authentication-on-api-views)"

echo "Created issue H-07: Authentication decorators"

gh issue create \
  --title "🟠 [HIGH] OnboardingProgress auto-creation fails" \
  --label "high,bug,backend,onboarding" \
  --body "## Issue H-08

**Location**: \`onboarding/views.py\` Lines 35-40

\`\`\`python
company = serializer.save()  # Fails - no tenant!
OnboardingProgress.objects.create(
    tenant=company.tenant,  # company.tenant doesn't exist
    # ...
)
\`\`\`

**Problem**: When company is saved, it doesn't have a tenant (see C-04), so OnboardingProgress creation fails

## Fix Required

\`\`\`python
def perform_create(self, serializer):
    # Save company with tenant from request
    company = serializer.save(tenant=self.request.tenant)
    
    # Now create onboarding progress
    OnboardingProgress.objects.create(
        tenant=self.request.tenant,
        company=company,
        current_step='company_info',
        steps_completed=[]
    )
\`\`\`

**Priority**: HIGH - Onboarding doesn't work
**Estimated Time**: 1 hour
**Dependencies**: C-01 (multi-tenancy), C-04 (tenant workflow)

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-08-onboardingprogress-auto-creation-fails)"

echo "Created issue H-08: OnboardingProgress"

gh issue create \
  --title "🟠 [HIGH] Chat session creation fails" \
  --label "high,bug,backend,ai-services" \
  --body "## Issue H-09

**Location**: \`ai_services/views.py\` Lines 55-61

**Problem**: Same tenant issue - \`request.tenant\` doesn't exist when multi-tenancy is disabled

\`\`\`python
session = ChatSession.objects.create(
    tenant=request.tenant,  # Fails!
    user=request.user,
    title='New Chat'
)
\`\`\`

## Fix Required

Once multi-tenancy is enabled (C-01), this should work automatically. Just need to ensure tenant is passed correctly.

\`\`\`python
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def chat_endpoint(request):
    session_id = request.data.get('session_id')
    
    if not session_id:
        # Create new session with tenant
        session = ChatSession.objects.create(
            tenant=request.tenant,
            user=request.user,
            title='New Chat'
        )
    else:
        # Get existing session for this tenant
        session = ChatSession.objects.get(
            id=session_id,
            tenant=request.tenant,  # Ensure tenant isolation
            user=request.user
        )
    
    # ... rest of chat logic
\`\`\`

**Priority**: HIGH - Chat doesn't work
**Estimated Time**: 1 hour
**Dependencies**: C-01 (multi-tenancy)

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-09-chat-session-creation-fails)"

echo "Created issue H-09: Chat session creation"

gh issue create \
  --title "🟠 [HIGH] Missing error handling in AI service" \
  --label "high,bug,backend,ai-services" \
  --body "## Issue H-10

**Location**: \`ai_services/services.py\`

**Problems**:
- No validation if API key is None
- Silent fallback hides errors
- No logging for exceptions
- No retry logic for transient failures

## Fix Required

\`\`\`python
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class GeminiAIService:
    def __init__(self):
        api_key = config('GOOGLE_API_KEY', default=None)
        if not api_key:
            logger.warning('GOOGLE_API_KEY not configured - AI features disabled')
            self.model = None
        else:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                logger.info('Gemini AI service initialized')
            except Exception as e:
                logger.error(f'Failed to initialize Gemini: {e}')
                self.model = None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def generate_brand_strategy(self, company_data: dict, tenant=None) -> dict:
        if not self.model:
            raise ValueError('AI service not available - check GOOGLE_API_KEY')
        
        try:
            # ... generation logic ...
            logger.info(f'Generated brand strategy (tokens: {token_count})')
            return result
            
        except Exception as e:
            logger.error(f'Failed to generate brand strategy: {e}')
            # Log to AIGeneration for monitoring
            AIGeneration.objects.create(
                tenant=tenant,
                generation_type='brand_strategy',
                status='failed',
                error_message=str(e)
            )
            raise
\`\`\`

Add \`status\` and \`error_message\` fields to AIGeneration model.

**Priority**: HIGH - Silent failures hide issues
**Estimated Time**: 3-4 hours
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-10-missing-error-handling-in-ai-service)"

echo "Created issue H-10: AI error handling"

gh issue create \
  --title "🟠 [HIGH] Missing component exports (TypeScript errors)" \
  --label "high,bug,frontend" \
  --body "## Issue H-11

**Locations**:
- \`components/chat/MessageBubble.tsx\` - Missing \`export\` on interfaces
- \`components/chat/FileSearch.tsx\` - Missing \`export\` on interfaces

**TypeScript Errors**:
\`\`\`
Cannot find module './MessageBubble' or its corresponding type declarations.
Cannot find module './FileSearch' or its corresponding type declarations.
\`\`\`

**Impact**: ChatInterface component fails to compile

## Fix Required

\`\`\`typescript
// MessageBubble.tsx
export interface Message {  // Add 'export'
  id: string;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
}

export interface MessageBubbleProps {  // Add 'export'
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  // ...
}
\`\`\`

Same for FileSearch.tsx

**Priority**: HIGH - Frontend doesn't compile
**Estimated Time**: 15 minutes
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-11-missing-component-exports)"

echo "Created issue H-11: Component exports"

gh issue create \
  --title "🟠 [HIGH] Field name mismatches (camelCase vs snake_case)" \
  --label "high,bug,backend,frontend,integration" \
  --body "## Issue H-12

**Location**: \`components/onboarding/CompanyForm.tsx\` + backend serializers

**Frontend sends**:
\`\`\`typescript
{
  targetAudience: '',  // camelCase
  coreProblem: ''
}
\`\`\`

**Backend expects** (\`onboarding/models.py\`):
\`\`\`python
target_audience = models.TextField()  # snake_case
core_problem = models.TextField()
\`\`\`

**Impact**: Backend receives empty values, validation may pass but data is lost

## Fix Required

### Option 1: Frontend converts (Recommended)
\`\`\`typescript
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  
  const apiData = {
    name: formData.name,
    industry: formData.industry,
    target_audience: formData.targetAudience,  // Convert to snake_case
    core_problem: formData.coreProblem,
    // ... convert all fields
  };
  
  await apiClient.post('/api/v1/companies/', apiData);
};
\`\`\`

### Option 2: Backend serializer accepts both
\`\`\`python
class CompanySerializer(serializers.ModelSerializer):
    targetAudience = serializers.CharField(source='target_audience', required=False)
    coreProblem = serializers.CharField(source='core_problem', required=False)
    
    class Meta:
        model = Company
        fields = '__all__'
\`\`\`

**Priority**: HIGH - Data not saving correctly
**Estimated Time**: 2-3 hours
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-12-field-name-mismatches-camelcase-vs-snake_case)"

echo "Created issue H-12: Field name mismatches"

gh issue create \
  --title "🟠 [HIGH] API client missing comprehensive error handling" \
  --label "high,bug,frontend" \
  --body "## Issue H-13

**Location**: \`lib/api.ts\`

**Problems**:
- Only handles 401 status
- No handling for 400, 403, 500 errors
- No retry logic for network failures
- No response body parsing helpers

## Fix Required

\`\`\`typescript
class APIClient {
  private async request(endpoint: string, options: RequestInit = {}) {
    const url = \`\${this.baseURL}\${endpoint}\`;
    const token = localStorage.getItem('access_token');
    
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': \`Bearer \${token}\` }),
      ...options.headers,
    };
    
    try {
      const response = await fetch(url, { ...options, headers });
      
      // Handle different status codes
      if (response.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/auth/login';
        throw new Error('Unauthorized');
      }
      
      if (response.status === 403) {
        throw new Error('Forbidden - insufficient permissions');
      }
      
      if (response.status >= 500) {
        throw new Error('Server error - please try again later');
      }
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || \`Request failed: \${response.status}\`);
      }
      
      return await response.json();
      
    } catch (error) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Network error - check your connection');
      }
      throw error;
    }
  }
  
  // Add retry logic
  async post(endpoint: string, data: any, retries = 3) {
    for (let i = 0; i < retries; i++) {
      try {
        return await this.request(endpoint, {
          method: 'POST',
          body: JSON.stringify(data),
        });
      } catch (error) {
        if (i === retries - 1) throw error;
        await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
      }
    }
  }
}
\`\`\`

**Priority**: HIGH - Poor error UX
**Estimated Time**: 2-3 hours
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-13-api-client-missing-error-handling)"

echo "Created issue H-13: API error handling"

gh issue create \
  --title "🟠 [HIGH] Missing authentication guards on protected pages" \
  --label "high,security,frontend" \
  --body "## Issue H-14

**Location**: All page components (dashboard, chat, onboarding)

**Problem**: No check for JWT token in localStorage

**Impact**: Unauthenticated users can access protected pages (until API call fails)

## Fix Required

\`\`\`typescript
// hooks/useAuth.ts
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export function useAuth() {
  const router = useRouter();
  
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/auth/login');
    }
  }, [router]);
  
  return {
    isAuthenticated: !!localStorage.getItem('access_token'),
    logout: () => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      router.push('/auth/login');
    }
  };
}

// In each protected page
'use client';
import { useAuth } from '@/hooks/useAuth';

export default function DashboardPage() {
  useAuth(); // Redirects if not authenticated
  
  return (
    <div>Protected content</div>
  );
}
\`\`\`

**Priority**: HIGH - Security issue
**Estimated Time**: 1-2 hours
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-14-missing-authentication-guards)"

echo "Created issue H-14: Authentication guards"

gh issue create \
  --title "🟠 [HIGH] Hardcoded company ID fallback in BrandForm" \
  --label "high,bug,frontend" \
  --body "## Issue H-15

**Location**: \`components/onboarding/BrandForm.tsx\` Line 29

\`\`\`typescript
const companyId = localStorage.getItem('company_id') || '1';  // ⚠️ Dangerous!
\`\`\`

**Problem**: Falls back to company ID 1 if not found

**Impact**: User might update wrong company's data

## Fix Required

\`\`\`typescript
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  
  const companyId = localStorage.getItem('company_id');
  if (!companyId) {
    alert('Company not found - please complete step 1 first');
    router.push('/onboarding/step-1');
    return;
  }
  
  try {
    await apiClient.put(\`/api/v1/companies/\${companyId}/\`, formData);
    router.push('/onboarding/step-3');
  } catch (error) {
    console.error('Failed to update company:', error);
    alert('Failed to update company');
  }
};
\`\`\`

**Priority**: HIGH - Data integrity issue
**Estimated Time**: 30 minutes
**Dependencies**: None

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#h-15-hardcoded-company-id-fallback)"

echo "Created issue H-15: Company ID fallback"

# Create remaining issues (Medium and Low priority)
# Due to character limits, I'll create these in batches

gh issue create \
  --title "🟡 [MEDIUM] Missing token refresh logic" \
  --label "medium,feature,frontend,authentication" \
  --body "## Issue M-16

**Location**: \`lib/api.ts\`

**Problem**: No automatic token refresh using \`refresh_token\`

**Impact**: Users logged out after access token expires (typically 60 minutes)

## Fix Required

Implement automatic token refresh before API calls if token is about to expire.

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md)"

echo "Created issue M-16: Token refresh"

gh issue create \
  --title "🟡 [MEDIUM] Missing onboarding steps 3-5" \
  --label "medium,feature,frontend,onboarding" \
  --body "## Issue M-17

**Exists**: step-1, step-2  
**Missing**: step-3, step-4, step-5

**StepWizard** shows 5 steps but only 2 implemented

**Required**:
- Step 3: Brand strategy generation
- Step 4: Brand identity generation  
- Step 5: Review and finalize

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md)"

echo "Created issue M-17: Onboarding steps 3-5"

gh issue create \
  --title "🟡 [MEDIUM] Dashboard data is static (no API integration)" \
  --label "medium,bug,frontend,dashboard" \
  --body "## Issue M-18

**Location**: \`components/dashboard/*\`

**Problem**: All data is hardcoded, no API calls

**Impact**: Dashboard doesn't reflect real user data

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md)"

echo "Created issue M-18: Dashboard API integration"

# Create summary issue for tracking
gh issue create \
  --title "📋 [META] Implementation Tracking - All 63 Issues" \
  --label "meta,tracking" \
  --body "## Implementation Plan Tracking

This is a meta-issue to track progress on all 63 issues identified in the codebase analysis.

See full details: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](../CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md)

## Phase 1: Critical Fixes (Week 1) - BLOCKING

- [ ] #C-01 - Multi-tenancy middleware enabled but broken
- [ ] #C-02 - No user registration endpoint  
- [ ] #C-03 - JWT login email/username mismatch
- [ ] #C-04 - No tenant creation workflow

**Estimated**: 15 hours

## Phase 2: High Priority (Week 2-3)

- [ ] #H-01 through #H-15 (20 issues)

**Estimated**: 30 hours

## Phase 3: Testing (Week 4)

- [ ] Backend test suite (70% coverage)
- [ ] Frontend test suite (60% coverage)
- [ ] Integration tests

**Estimated**: 43 hours

## Phase 4: Medium/Low Priority (Week 5-6)

- [ ] Remaining 28 issues
- [ ] Production readiness
- [ ] Documentation

**Total Timeline**: 4-6 weeks

---

**Note**: Additional issues for Medium/Low priority items (M-01 through M-25, L-01 through L-14) will be created as we progress through Phase 1-2."

echo ""
echo "✅ Successfully created GitHub issues for AI Brand Automator!"
echo ""
echo "Summary:"
echo "- 4 Critical issues (🔴 BLOCKING)"
echo "- 15 High priority issues (🟠)"
echo "- 3 Medium priority issues (🟡)"
echo "- 1 Meta tracking issue (📋)"
echo ""
echo "Total created: 23 issues (more to be created as we progress)"
echo ""
echo "View all issues: gh issue list"
