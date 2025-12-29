# 患者数据处理接口升级说明

## 修改日期
2025-12-29

## 修改概述
为 `POST /api/patient_data/process_patient_data_smart` 接口添加 JWT 认证和权限管理功能，利用现有的 `bus_user_patient_access` 表。

## 主要变更

### 1. 认证方式升级

#### 1.1 支持 JWT Token 认证（推荐）
- **传递方式**：在 `Authorization` header 中传递 JWT token
- **格式**：`Authorization: Bearer <token>`
- **算法**：HS256（对称加密）
- **密钥**：`DH4neb6Aipe1ortdalusvo8iosQiBIYupLNPTu3j40PZ9tBbLrPD4mAmDVsB7nZw`
- **Token payload**：需要包含 `sub`、`user_id` 或 `userId` 字段来标识用户

#### 1.2 兼容 user_id 参数（备选）
- 如果没有提供 token，可以在请求体中传递 `user_id`
- 优先级：Token > 请求体中的 user_id

### 2. 数据库变更

**无需执行数据库迁移** - 使用现有的 `bus_user_patient_access` 表

现有表结构：
- `id`: VARCHAR(64) - 主键ID
- `user_id`: VARCHAR(64) - 用户ID
- `patient_id`: VARCHAR(64) - 患者ID（外键关联 bus_patient）
- `role`: VARCHAR(50) - 角色（owner/editor/viewer）
- `can_edit`: BOOLEAN - 是否可以编辑
- `can_delete`: BOOLEAN - 是否可以删除
- `can_share`: BOOLEAN - 是否可以分享
- `granted_by`: VARCHAR(64) - 授权人ID
- `granted_at`: TIMESTAMP - 授权时间
- `expires_at`: TIMESTAMP - 过期时间（NULL表示永不过期）
- `is_active`: BOOLEAN - 是否激活
- `created_at`: TIMESTAMP - 创建时间

### 3. 代码变更

#### 3.1 安全模块（app/core/security.py）
- 新增 `JWT_SECRET_KEY` 和 `JWT_ALGORITHM` 配置
- 新增 `decode_external_token()` 方法
  - 支持解码外部系统的 JWT token
  - 自动从 `sub`、`user_id`、`userId` 字段中提取用户ID
  - 验证失败返回 None

#### 3.2 ORM 模型（app/models/bus_models.py）
- 新增 `UserPatientAccess` 类，映射到现有的 `bus_user_patient_access` 表
- 字段完全匹配数据库实际结构

#### 3.3 业务逻辑（app/models/bus_patient_helpers.py）
- 新增 `create_user_patient_access()` 方法
  - 创建或更新用户患者访问权限记录
  - 默认角色为 `owner`（所有者）
  - 参数：
    - `role`: "owner" / "editor" / "viewer"（默认 owner）
    - `can_edit`: 是否可编辑（默认 True）
    - `can_delete`: 是否可删除（默认 False）
    - `can_share`: 是否可分享（默认 False）

#### 3.4 API 接口（app/routers/patient_data_processing.py）
- 修改 `process_patient_data_smart()` 接口
  - 新增 `authorization` header 参数（可选）
  - 修改 `user_id` 为可选参数
  - 添加 token 解析逻辑
  - 优先级：Token > 请求体中的 user_id

- 修改 `smart_stream_patient_data_processing()` 函数
  - 创建患者后自动创建访问权限记录
  - 默认授予上传用户 `owner` 角色（所有者）

- 修改 `process_patient_data_background_from_task()` 后台任务函数
  - 同步添加权限创建逻辑

#### 3.5 API 文档（API_TEST_DOCUMENTATION.md）
- 更新接口文档，说明 JWT 认证方式
- 提供两种请求示例：使用 Token 和使用 user_id

### 4. 功能说明

#### 4.1 认证流程
1. 接口接收到请求
2. 检查 `Authorization` header
3. 如果有 token，解析并验证
4. 从 token 中提取 `user_id`
5. 如果没有 token 或解析失败，从请求体获取 `user_id`
6. 如果两者都没有，返回 400 错误

#### 4.2 权限自动授予机制
当用户通过 `POST /api/patient_data/process_patient_data_smart` 创建患者时：
1. 系统创建患者记录
2. 自动在 `bus_user_patient_access` 表中创建权限记录
3. 默认权限配置：
   - `role`: "owner"（所有者）
   - `can_edit`: true
   - `can_delete`: false
   - `can_share`: false
   - `granted_by`: 用户自己的 user_id
   - `is_active`: true

#### 4.3 created_by 字段
- `bus_patient.created_by`: 使用 `user_id`
- `bus_patient_structured_data.created_by`: 使用 `user_id`
- 所有患者相关数据的创建者都正确关联到上传用户

## API 使用示例

### 请求示例 1（推荐：使用 Token）
```bash
curl -X POST http://localhost:9527/api/patient_data/process_patient_data_smart \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwidXNlcl9pZCI6Ijc1IiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c" \
  -d '{
    "patient_description": "患者李云山的完整病例资料",
    "consultation_purpose": "多学科会诊",
    "files": [...]
  }'
```

### 请求示例 2（备选：使用 user_id）
```bash
curl -X POST http://localhost:9527/api/patient_data/process_patient_data_smart \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "75",
    "patient_description": "患者李云山的完整病例资料",
    "consultation_purpose": "多学科会诊",
    "files": [...]
  }'
```

### 错误处理
- 如果既没有提供 token 也没有提供 user_id，返回 400 错误：
  ```json
  {
    "detail": "缺少 user_id：请在 Authorization header 中提供有效的 token，或在请求体中提供 user_id"
  }
  ```

## 环境配置

**必需配置**：在 `.env` 文件中配置以下变量

```env
# External JWT Verification (外部系统 Token 验证)
JWT_SECRET_KEY=DH4neb6Aipe1ortdalusvo8iosQiBIYupLNPTu3j40PZ9tBbLrPD4mAmDVsB7nZw
JWT_ALGORITHM=HS256
```

**配置说明**：
- `JWT_SECRET_KEY`：用于验证外部系统 JWT token 的密钥（必填）
- `JWT_ALGORITHM`：JWT 算法，支持 HS256 或 RS256（默认 HS256）

**安全提示**：
- ⚠️ 密钥已从代码中移除，必须在 `.env` 文件中配置
- 请勿将 `.env` 文件提交到版本控制系统
- `.env.example` 文件提供了配置模板

## 部署步骤

1. **配置环境变量**（必需）
   ```bash
   # 编辑 .env 文件
   vim .env

   # 添加或确认以下配置：
   # JWT_SECRET_KEY=DH4neb6Aipe1ortdalusvo8iosQiBIYupLNPTu3j40PZ9tBbLrPD4mAmDVsB7nZw
   # JWT_ALGORITHM=HS256
   ```

2. **重启应用服务**
   ```bash
   # 重启 uvicorn 或相应的应用服务
   systemctl restart mediwise_api
   ```

3. **验证功能**
   - 使用 JWT token 调用接口，确保能正确解析 user_id
   - 使用 user_id 调用接口，确保向后兼容
   - 检查 `bus_user_patient_access` 表是否正确创建权限记录
   - 检查日志，确认 token 解析过程

## 注意事项

1. **向后兼容性**：此修改向后兼容，现有使用 `user_id` 的调用方无需修改
2. **推荐使用 Token**：新的调用方建议使用 JWT token 认证方式
3. **Token 格式**：
   - 支持 `Authorization: Bearer <token>` 格式
   - 也支持 `Authorization: <token>` 格式（自动移除 Bearer 前缀）
4. **Token Payload**：确保 token 中包含用户标识字段（`sub`、`user_id` 或 `userId`）

## 后续优化建议

1. 支持 RS256 非对称加密算法（需要 RSA 公钥/私钥对）
2. 实现基于 `bus_user_patient_access` 的权限验证中间件
3. 添加权限管理接口（授权、撤销、查询等）
4. 支持权限过期时间管理
5. 添加权限变更审计日志
