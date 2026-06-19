#!/bin/bash

echo "Claude autonomous cycle start"

claude << 'EOF'
Read .ai/backlog.md
Pick first task
Implement
Run tests
Update progress
EOF
