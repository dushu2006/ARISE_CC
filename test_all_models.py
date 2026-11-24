import asyncio
from datetime import datetime, timezone, timedelta
from core.database.base import get_session
from core.database import models
from sqlalchemy import select

async def test():
    async with get_session() as session:
        # Test inserting a user
        user = models.User(username='comprehensive_test', email='comprehensive@example.com', full_name='Comprehensive Test', hashed_password='hash')
        session.add(user)
        await session.flush()
        print(f'Created user: {user.id}')

        # Test inserting a task
        task = models.Task(
            objective='Comprehensive test task',
            context_json={'key': 'value'},
            status=models.TaskStatus.CREATED,
            risk_level=models.RiskLevel.R1,
            required_capabilities_json=['test_capability'],
            granted_capabilities_json=['granted_capability'],
            priority='HIGH',
            metadata_json={'meta': 'data'}
        )
        session.add(task)
        await session.flush()
        print(f'Created task: {task.id}')
        print(f'  created_at: {task.created_at}')
        print(f'  updated_at: {task.updated_at}')

        # Test inserting an agent
        agent = models.Agent(
            name='Comprehensive Test Agent',
            type=models.AgentType.COORDINATOR,
            version='1.0.0',
            module_path='core.agents.coordinator',
            class_name='CentralCoordinator',
            capabilities_json=['cap1', 'cap2'],
            config_json={'config': 'value'}
        )
        session.add(agent)
        await session.flush()
        print(f'Created agent: {agent.id}')
        print(f'  created_at: {agent.created_at}')
        print(f'  updated_at: {agent.updated_at}')

        # Test inserting a memory
        memory = models.MemoryMetadata(
            kind=models.MemoryKind.SEMANTIC,
            source=models.MemorySource.USER,
            confidence=0.95,
            pii_detected=False,
            retention_expires_at=None,
            access_count=0,
            version=1,
            is_archived=False
        )
        session.add(memory)
        await session.flush()
        print(f'Created memory: {memory.id}')

        # Test inserting an event
        event = models.Event(
            event_type=models.EventType.TASK_CREATED,
            aggregate_id=task.id,
            aggregate_type='task',
            payload_json={'objective': task.objective},
            metadata_json={'source': 'test'},
            correlation_id='test-correlation-id',
            version=1
        )
        session.add(event)
        await session.flush()
        print(f'Created event: {event.id}')

        # Test inserting a policy
        policy = models.Policy(
            name='Test Policy',
            description='Test policy description',
            risk_level=models.PolicyRiskLevel.R1,
            capabilities_json=['test_cap'],
            is_active=True,
            priority=10
        )
        session.add(policy)
        await session.flush()
        print(f'Created policy: {policy.id}')

        # Test inserting a model provider
        provider = models.ModelProvider(
            name='Test Provider',
            type=models.ProviderType.OPENAI,
            api_key='sk-test',
            default_model='gpt-4o',
            models_json={},
            max_tokens=4096,
            timeout=60.0,
            max_retries=3,
            supports_streaming=True,
            supports_functions=True,
            supports_vision=False,
            supports_audio=False,
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03,
            rpm_limit=60,
            tpm_limit=100000,
            is_active=True
        )
        session.add(provider)
        await session.flush()
        print(f'Created provider: {provider.id}')

        # Test inserting a voice session
        voice_session = models.VoiceSession(
            user_id='test_user',
            privacy_mode=models.PrivacyMode.STANDARD,
            language='en',
            started_at=datetime.now(timezone.utc),
            total_interactions=0,
            total_audio_duration_ms=0,
            status=models.VoiceSessionStatus.ACTIVE,
            metadata_json={}
        )
        session.add(voice_session)
        await session.flush()
        print(f'Created voice session: {voice_session.id}')

        # Test inserting a workflow
        workflow = models.Workflow(
            name='Test Workflow',
            description='Test workflow description',
            steps_json=[{'step': 1, 'action': 'test'}],
            status=models.WorkflowStatus.PENDING,
            metadata_json={}
        )
        session.add(workflow)
        await session.flush()
        print(f'Created workflow: {workflow.id}')

        # Test inserting credentials
        cred = models.CredentialMetadata(
            category=models.CredentialCategory.API_KEYS,
            key='test_key',
            target_name='test_target',
            description='Test credential',
            expires_at=None,
            rotation_required=False,
            metadata_json={}
        )
        session.add(cred)
        await session.flush()
        print(f'Created credential: {cred.id}')

        # Test inserting a network rule
        net_rule = models.NetworkRule(
            name='Test Rule',
            action=models.NetworkAction.ALLOW,
            direction='outbound',
            protocol='tcp',
            port=443,
            destination='api.openai.com',
            description='Allow OpenAI API',
            is_active=True,
            priority=100
        )
        session.add(net_rule)
        await session.flush()
        print(f'Created network rule: {net_rule.id}')

        # Test inserting a setting
        setting = models.Setting(
            key='test.setting',
            value_json={'value': 'test'},
            value_type='object',
            description='Test setting',
            category=models.SettingCategory.APP,
            is_sensitive=False,
            is_runtime_mutable=True,
            validation_json=None,
            default_value_json={'value': 'default'},
            updated_by='test'
        )
        session.add(setting)
        await session.flush()
        print(f'Created setting: {setting.key}')

        # Test inserting a feature flag
        flag = models.FeatureFlag(
            key='test_flag',
            name='Test Flag',
            description='Test feature flag',
            flag_type=models.FlagType.BOOLEAN,
            default_value=False,
            enabled=True,
            rollout_percentage=100.0,
            targeting_rules_json=[],
            metadata_json={}
        )
        session.add(flag)
        await session.flush()
        print(f'Created feature flag: {flag.id}')

        # Test inserting an API key
        api_key = models.APIKey(
            name='Test API Key',
            key_hash='abc123',
            key_prefix='test_',
            scopes_json=['read', 'write'],
            user_id=user.id,
            expires_at=None,
            is_active=True,
            description='Test API key',
            metadata_json={}
        )
        session.add(api_key)
        await session.flush()
        print(f'Created API key: {api_key.id}')

        # Test inserting a user session
        user_session = models.UserSession(
            user_id=user.id,
            session_token_hash='session_hash_123',
            ip_address='127.0.0.1',
            user_agent='Test Agent',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            is_active=True,
            metadata_json={}
        )
        session.add(user_session)
        await session.flush()
        print(f'Created user session: {user_session.id}')

        # Test inserting an audit log
        audit = models.AuditLog(
            event_type=models.AuditEventType.TASK_OPERATION,
            timestamp=datetime.now(timezone.utc),
            user_id='test_user',
            session_id=None,
            task_id=task.id,
            agent_id=None,
            action='create_task',
            resource='tasks',
            capability=None,
            risk_level=models.RiskLevel.R1,
            success=True,
            error=None,
            context_json={'task_id': task.id},
            previous_hash=None,
            event_hash='hash123'
        )
        session.add(audit)
        await session.flush()
        print(f'Created audit log: {audit.id}')

        # Test inserting evidence
        evidence = models.Evidence(
            task_id=task.id,
            agent_id=None,
            interaction_id=None,
            type=models.EvidenceType.LOG,
            description='Test evidence',
            file_path='logs/test.log',
            file_size_bytes=1024,
            mime_type='text/plain',
            checksum_sha256='abc123',
            metadata_json={}
        )
        session.add(evidence)
        await session.flush()
        print(f'Created evidence: {evidence.id}')

        # Test inserting an evidence chain
        chain = models.EvidenceChain(
            task_id=task.id,
            name='Test Chain'
        )
        session.add(chain)
        await session.flush()
        print(f'Created evidence chain: {chain.id}')

        # Test inserting an evidence chain link
        chain_link = models.EvidenceChainLink(
            chain_id=chain.id,
            evidence_id=evidence.id,
            sequence=1
        )
        session.add(chain_link)
        await session.flush()
        print(f'Created evidence chain link')

        # Test inserting a task checkpoint
        checkpoint = models.TaskCheckpoint(
            task_id=task.id,
            step=1,
            state='RUNNING',
            context_json={'step': 1},
            executed_actions_json=[],
            is_latest=True
        )
        session.add(checkpoint)
        await session.flush()
        print(f'Created checkpoint: {checkpoint.id}')

        # Test inserting a task dependency
        task2 = models.Task(
            objective='Dependent task',
            context_json={},
            status=models.TaskStatus.CREATED,
            risk_level=models.RiskLevel.R0,
            required_capabilities_json=[],
            granted_capabilities_json=[],
            priority='NORMAL',
            metadata_json={}
        )
        session.add(task2)
        await session.flush()

        dep = models.TaskDependency(
            task_id=task2.id,
            depends_on_task_id=task.id,
            dependency_type='sequential'
        )
        session.add(dep)
        await session.flush()
        print(f'Created task dependency')

        # Test inserting a task approval
        approval = models.TaskApproval(
            task_id=task.id,
            capability='test_capability',
            risk_level=models.RiskLevel.R2,
            resource='test_resource',
            description='Test approval',
            requested_at=datetime.now(timezone.utc),
            approved=None,
            granted_by=None,
            grant_scope='task',
            grant_duration_hours=24,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            grant_id=None
        )
        session.add(approval)
        await session.flush()
        print(f'Created task approval: {approval.id}')

        # Test inserting a task event
        task_event = models.TaskEvent(
            task_id=task.id,
            event_type='state_change',
            from_state='CREATED',
            to_state='RUNNING',
            step=1,
            message='Task started',
            details_json={}
        )
        session.add(task_event)
        await session.flush()
        print(f'Created task event: {task_event.id}')

        # Test inserting a scheduled task
        scheduled = models.ScheduledTask(
            name='Daily Task',
            cron_expression='0 0 * * *',
            objective='Daily scheduled task',
            context_json={},
            enabled=True,
            timezone='UTC',
            max_catchup_runs=1,
            metadata_json={}
        )
        session.add(scheduled)
        await session.flush()
        print(f'Created scheduled task: {scheduled.id}')

        # Test inserting a consolidation run
        consolidation = models.ConsolidationRun(
            kind='working_to_episodic',
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            input_count=100,
            output_count=10,
            status='running',
            error=None,
            config_json={}
        )
        session.add(consolidation)
        await session.flush()
        print(f'Created consolidation run: {consolidation.id}')

        # Test inserting a security event
        security = models.SecurityEvent(
            event_id=audit.id,
            severity=models.SecuritySeverity.LOW,
            category='config',
            source_ip='127.0.0.1',
            user_agent='Test',
            mitre_technique=None,
            response_action='logged',
            acknowledged=False,
            acknowledged_at=None,
            acknowledged_by=None
        )
        session.add(security)
        await session.flush()
        print(f'Created security event')

        # Test inserting agent health
        agent_health = models.AgentHealth(
            agent_id=agent.id,
            status=models.AgentStatus.HEALTHY,
            last_heartbeat=datetime.now(timezone.utc),
            consecutive_failures=0,
            total_executions=0,
            successful_executions=0,
            avg_execution_time_ms=None,
            last_error=None,
            last_error_at=None,
            cpu_percent=10.5,
            memory_mb=50.0
        )
        session.add(agent_health)
        await session.flush()
        print(f'Created agent health')

        # Test inserting agent execution
        agent_exec = models.AgentExecution(
            agent_id=agent.id,
            task_id=task.id,
            delegation_id=None,
            objective='Test execution',
            status='completed',
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            execution_time_ms=1000,
            result_json={'result': 'ok'},
            error=None,
            evidence_count=0,
            verification_status='verified',
            verification_issues_json=None
        )
        session.add(agent_exec)
        await session.flush()
        print(f'Created agent execution: {agent_exec.id}')

        # Test inserting model usage
        usage = models.ModelUsage(
            provider_id=provider.id,
            model='gpt-4o',
            task_id=task.id,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=500,
            success=True,
            error=None
        )
        session.add(usage)
        await session.flush()
        print(f'Created model usage: {usage.id}')

        # Test inserting model cost
        cost = models.ModelCost(
            provider_id=provider.id,
            model='gpt-4o',
            date='2026-11-10',
            input_tokens=100,
            output_tokens=50,
            input_cost=0.001,
            output_cost=0.0015,
            total_cost=0.0025,
            request_count=1
        )
        session.add(cost)
        await session.flush()
        print(f'Created model cost: {cost.id}')

        # Test inserting a capability grant
        grant = models.CapabilityGrant(
            policy_id=policy.id,
            capability='test_capability',
            resource='test_resource',
            granted_to='user',
            granted_by='admin',
            scope='session',
            duration_hours=24,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_active=True,
            conditions_json={}
        )
        session.add(grant)
        await session.flush()
        print(f'Created capability grant: {grant.id}')

        # Test inserting policy audit log
        policy_audit = models.PolicyAuditLog(
            policy_id=policy.id,
            capability='test_capability',
            resource='test_resource',
            requested_by='user',
            decision='granted',
            reason='Auto-approved for development',
            context_json={}
        )
        session.add(policy_audit)
        await session.flush()
        print(f'Created policy audit log: {policy_audit.id}')

        # Test inserting an event projection
        projection = models.EventProjection(
            projection_name='task_summary',
            last_event_id=event.id,
            last_processed_at=datetime.now(timezone.utc),
            status='running',
            error=None,
            checkpoint_json={}
        )
        session.add(projection)
        await session.flush()
        print(f'Created event projection: {projection.id}')

        # Test inserting a voice interaction
        voice_interaction = models.VoiceInteraction(
            session_id=voice_session.id,
            sequence=1,
            wake_word_confidence=0.95,
            asr_transcript='test command',
            asr_confidence=0.9,
            asr_language='en',
            asr_duration_ms=500,
            intent_type='command',
            intent_confidence=0.95,
            intent_entities_json={'entity': 'test'},
            intent_duration_ms=100,
            risk_level=models.RiskLevel.R0,
            task_id=None,
            tts_provider='test',
            tts_duration_ms=200,
            tts_audio_size_bytes=1024,
            barge_in=False,
            total_duration_ms=800
        )
        session.add(voice_interaction)
        await session.flush()
        print(f'Created voice interaction: {voice_interaction.id}')

        # Test inserting a UI element
        ui_element = models.UIElement(
            workflow_id=workflow.id,
            selector='button#submit',
            element_type='button',
            text='Submit',
            attributes_json={'id': 'submit', 'type': 'button'},
            bounding_box_json={'x': 100, 'y': 200, 'width': 80, 'height': 30},
            screenshot_path=None,
            is_interactive=True,
            confidence=0.99
        )
        session.add(ui_element)
        await session.flush()
        print(f'Created UI element: {ui_element.id}')

        # Test inserting a security audit log
        sec_audit = models.SecurityAuditLog(
            event_type='credential_access',
            severity=models.SecuritySeverity.MEDIUM,
            user_id='test_user',
            agent_id=agent.id,
            task_id=task.id,
            action='read_credential',
            resource='api_key',
            capability='credential.read',
            risk_level=models.RiskLevel.R2,
            success=True,
            error=None,
            source_ip='127.0.0.1',
            user_agent='Test',
            mitre_technique='T1552',
            response_action='logged',
            acknowledged=False,
            acknowledged_at=None,
            acknowledged_by=None,
            context_json={}
        )
        session.add(sec_audit)
        await session.flush()
        print(f'Created security audit log: {sec_audit.id}')

        # Test inserting setting history
        history = models.SettingHistory(
            key='test.setting',
            old_value_json={'value': 'old'},
            new_value_json={'value': 'new'},
            changed_at=datetime.now(timezone.utc),
            changed_by='test',
            reason='Test change'
        )
        session.add(history)
        await session.flush()
        print(f'Created setting history: {history.id}')

        await session.commit()
        print('\nAll models inserted and committed successfully!')

        # Verify counts
        result = await session.execute(select(models.User))
        users = result.scalars().all()
        print(f'Users: {len(users)}')

        result = await session.execute(select(models.Task))
        tasks = result.scalars().all()
        print(f'Tasks: {len(tasks)}')

        result = await session.execute(select(models.Agent))
        agents = result.scalars().all()
        print(f'Agents: {len(agents)}')

        result = await session.execute(select(models.MemoryMetadata))
        memories = result.scalars().all()
        print(f'Memories: {len(memories)}')

        result = await session.execute(select(models.Event))
        events = result.scalars().all()
        print(f'Events: {len(events)}')

        result = await session.execute(select(models.Policy))
        policies = result.scalars().all()
        print(f'Policies: {len(policies)}')

        result = await session.execute(select(models.ModelProvider))
        providers = result.scalars().all()
        print(f'Providers: {len(providers)}')

        result = await session.execute(select(models.VoiceSession))
        voice_sessions = result.scalars().all()
        print(f'Voice Sessions: {len(voice_sessions)}')

        result = await session.execute(select(models.Workflow))
        workflows = result.scalars().all()
        print(f'Workflows: {len(workflows)}')

        result = await session.execute(select(models.CredentialMetadata))
        creds = result.scalars().all()
        print(f'Credentials: {len(creds)}')

        result = await session.execute(select(models.NetworkRule))
        net_rules = result.scalars().all()
        print(f'Network Rules: {len(net_rules)}')

        result = await session.execute(select(models.Setting))
        settings = result.scalars().all()
        print(f'Settings: {len(settings)}')

        result = await session.execute(select(models.FeatureFlag))
        flags = result.scalars().all()
        print(f'Feature Flags: {len(flags)}')

        result = await session.execute(select(models.APIKey))
        api_keys = result.scalars().all()
        print(f'API Keys: {len(api_keys)}')

        result = await session.execute(select(models.UserSession))
        user_sessions = result.scalars().all()
        print(f'User Sessions: {len(user_sessions)}')

        result = await session.execute(select(models.AuditLog))
        audit_logs = result.scalars().all()
        print(f'Audit Logs: {len(audit_logs)}')

        result = await session.execute(select(models.Evidence))
        evidence_list = result.scalars().all()
        print(f'Evidence: {len(evidence_list)}')

        result = await session.execute(select(models.EvidenceChain))
        chains = result.scalars().all()
        print(f'Evidence Chains: {len(chains)}')

asyncio.run(test())