import sys
sys.path.insert(0, "D:/Projects/ARISE_CC")

try:
    from core.database import Base, Task, Agent, init_db, get_database_manager
    print("[OK] Imports work!")
except Exception as e:
    print("[FAIL] Import failed: " + str(e))
    sys.exit(1)

# Test that all expected models are available
expected_models = [
    'Task', 'TaskCheckpoint', 'TaskDependency', 'TaskApproval', 'ScheduledTask', 'TaskEvent',
    'Agent', 'AgentHealth', 'AgentExecution',
    'MemoryMetadata', 'ConsolidationRun',
    'Event', 'EventProjection',
    'Policy', 'CapabilityGrant', 'PolicyAuditLog',
    'ModelProvider', 'ModelUsage', 'ModelCost',
    'VoiceSession', 'VoiceInteraction',
    'Workflow', 'UIElement',
    'CredentialMetadata', 'NetworkRule', 'SecurityAuditLog',
    'Setting', 'SettingHistory',
    'FeatureFlag',
    'APIKey',
    'User', 'UserSession',
    'AuditLog', 'SecurityEvent',
    'Evidence', 'EvidenceChain', 'EvidenceChainLink',
]

for model in expected_models:
    if not hasattr(sys.modules['core.database.models'], model):
        print("[FAIL] Missing model: " + model)
        sys.exit(1)

print("[OK] All models available!")
print("[OK] Database package complete!")