# 患者数据处理接口升级说明

## 修改日期
2025-12-29

## 修改概述
为 `POST /api/patient_data/process_patient_data_smart` 接口添加用户身份验证和权限管理功能，利用现有的 `bus_user_patient_access` 表。

## 主要变更

### 1. 数据库变更

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

### 2. 代码变更

#### 2.1 ORM 模型（app/models/bus_models.py）
- 新增 `UserPatientAccess` 类，映射到现有的 `bus_user_patient_access` 表
- 字段完全匹配数据库表结构

#### 2.2 业务逻辑（app/models/bus_patient_helpers.py）
- 新增 `create_user_patient_access()` 方法
  - 创建或更新用户患者访问权限记录
  - 自动检测重复记录并更新
  - 默认角色为 `editor`（编辑者）
  - 参数：
    - `role`: "owner" / "editor" / "viewer"
    - `can_edit`: 是否可编辑（默认 True）
    - `can_delete`: 是否可删除（默认 False）
    - `can_share`: 是否可分享（默认 False）

#### 2.3 API 接口（app/routers/patient_data_processing.py）
- 修改 `process_patient_data_smart()` 接口
  - **新增必填参数**：`user_id`
  - 添加 `user_id` 验证逻辑

- 修改 `smart_stream_patient_data_processing()` 函数
  - 创建患者后自动创建访问权限记录
  - 默认授予上传用户 `editor` 角色

- 修改 `process_patient_data_background_from_task()` 后台任务函数
  - 同步添加权限创建逻辑

#### 2.4 API 文档（API_TEST_DOCUMENTATION.md）
- 更新接口文档，说明 `user_id` 为必填参数
- 添加权限说明：创建患者后会自动授予创建用户 editor 权限

### 3. 功能说明

#### 3.1 权限自动授予机制
当用户通过 `POST /api/patient_data/process_patient_data_smart` 创建患者时：
1. 系统创建患者记录
2. 自动在 `bus_user_patient_access` 表中创建权限记录
3. 默认权限配置：
   - `role`: "editor"
   - `can_edit`: true
   - `can_delete`: false
   - `can_share`: false
   - `granted_by`: 用户自己的 user_id
   - `is_active`: true

#### 3.2 created_by 字段
- `bus_patient.created_by`: 使用 `user_id`
- `bus_patient_structured_data.created_by`: 使用 `user_id`
- 所有患者相关数据的创建者都正确关联到上传用户

## API 使用示例

### 请求示例
```bash
curl -X POST http://localhost:9527/api/patient_data/process_patient_data_smart \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_12345",
    "patient_description": "患者李云山的完整病例资料",
    "consultation_purpose": "多学科会诊",
    "files": [
      {
        "file_name": "检查报告.pdf",
        "file_content": "base64_encoded_content..."
      }
    ]
  }'
```

### 错误处理
- 如果未提供 `user_id`，返回 400 错误：
  ```json
  {
    "detail": "user_id 不能为空"
  }
  ```

## 部署步骤

**无需数据库迁移** - 直接重启应用即可

1. **重启应用服务**
   ```bash
   # 重启 uvicorn 或相应的应用服务
   systemctl restart mediwise_api
   ```

2. **验证功能**
   - 调用接口创建患者，确保 `user_id` 参数生效
   - 检查 `bus_user_patient_access` 表是否正确创建权限记录
   - 检查 `bus_patient.created_by` 和 `bus_patient_structured_data.created_by` 字段是否正确

## 注意事项

1. **向后兼容性**：此修改不向后兼容，所有调用方必须传入 `user_id` 参数
2. **权限验证**：当前版本仅创建权限记录，暂未实现权限验证逻辑（后续可扩展）
3. **数据迁移**：现有患者的 `created_by` 字段可能为空，需要单独处理历史数据

## 后续优化建议

1. 实现基于 `bus_user_patient_access` 的权限验证中间件
2. 添加权限管理接口（授权、撤销、查询等）
3. 支持权限过期时间管理
4. 添加权限变更审计日志
