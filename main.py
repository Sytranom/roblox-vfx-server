--!strict
-- /Modules/Panels/VFXViewportController.lua (Corrected Version)

-- Shared & Core Modules
local Janitor = require(script.Parent.Parent.Shared.Janitor)
local ViewportEmitter = require(script.Parent.ViewportEmitter)

local VFXViewportController = {}
VFXViewportController.__index = VFXViewportController

local BUFFER_ROWS = 2
local PADDING = 10
local DEFAULT_CAMERA_FOV = 50
local DEFAULT_CAMERA_DISTANCE = 25

local function deserialize(dataType, dataValue)
	if dataType == "ColorSequence" then
		local keypoints = {}
		for _, kp in ipairs(dataValue) do
			table.insert(keypoints, ColorSequenceKeypoint.new(kp.Time, Color3.new(unpack(kp.Value))))
		end
		return ColorSequence.new(keypoints)
	elseif dataType == "NumberSequence" then
		local keypoints = {}
		for _, kp in ipairs(dataValue) do
			table.insert(keypoints, NumberSequenceKeypoint.new(kp.Time, kp.Value, kp.Envelope))
		end
		return NumberSequence.new(keypoints)
	elseif dataType == "NumberRange" then
		return NumberRange.new(dataValue.Min, dataValue.Max)
	end
	return nil
end

function VFXViewportController.new(scrollingFrame, addButton, vfxTemplate)
	local self = setmetatable({}, VFXViewportController)
	self.janitor = Janitor.new()
	self.frame = scrollingFrame
	self.addButton = addButton
	self.template = vfxTemplate
	self.eventJanitor = nil
	self.addButton.AnchorPoint = Vector2.new(0, 0)
	self.addButton.Parent = nil
	self.addButton.Visible = false
	if self.template then self.template.Visible = false end
	self.dataSource = {}
	self.activeItems = {}
	self.inactivePool = {}
	self.itemsPerRow = 1
	self.totalRows = 0
	self.cellSize = 128
	self.updateLayoutRequested = false
	self.isActive = false
	return self
end

function VFXViewportController:Activate()
	if self.isActive then return end
	self.isActive = true
	self.frame.Visible = true
	self.addButton.Parent = self.frame
	self.addButton.Visible = true
	self.eventJanitor = Janitor.new()
	self:_setupListeners()
	self:recalculateLayout()
end

function VFXViewportController:Deactivate()
	if not self.isActive then return end
	self.isActive = false
	self.frame.Visible = false
	self.addButton.Parent = nil
	self.addButton.Visible = false
	if self.eventJanitor then
		self.eventJanitor:Cleanup()
		self.eventJanitor = nil
	end
	self:_clearAllItems()
	self.frame.CanvasSize = UDim2.fromScale(0, 0)
end

function VFXViewportController:setDataSource(data)
	self:_clearAllItems()
	self.dataSource = data or {}
	if self.isActive then
		self:recalculateLayout()
	end
end

function VFXViewportController:_loadItem(dataIndex)
	if self.activeItems[dataIndex] then return end
	local data = self.dataSource[dataIndex]
	if not data then return end

	local itemJanitor = self.eventJanitor:Add(Janitor.new())
	local instance = self:_getTemplateInstance()
	local viewportFrame = instance:FindFirstChild("Viewport", true)
	if not viewportFrame or not viewportFrame:IsA("ViewportFrame") then
		instance:Destroy()
		return
	end

	local worldModel = Instance.new("WorldModel")
	worldModel.Parent = viewportFrame
	itemJanitor:Add(worldModel)

	local hostPart = Instance.new("Part")
	hostPart.Name = "VFXHostPart"
	hostPart.Size = Vector3.new(1, 1, 1)
	hostPart.Anchored = true
	hostPart.CanCollide = false
	hostPart.Transparency = 1
	hostPart.Parent = worldModel

	local hostCamera = Instance.new("Camera")
	hostCamera.Name = "VFXHostCamera"
	hostCamera.Parent = worldModel
	viewportFrame.CurrentCamera = hostCamera

	-- Create a list of properties to process. This supports both old and new formats.
	local propertiesList = {}
	if data.Emitters and #data.Emitters > 0 then
		-- New format: A group of emitters
		propertiesList = data.Emitters
	elseif data.Properties then
		-- Old format: A single emitter
		table.insert(propertiesList, data.Properties)
	end

	if #propertiesList == 0 then
		instance:Destroy()
		return
	end

	-- Use the first emitter's properties to set up the camera as a default
	local firstProps = propertiesList[1]
	if firstProps.ParentCFrame then
		hostPart.CFrame = CFrame.new(unpack(firstProps.ParentCFrame))
	end
	if firstProps.CameraCFrame and firstProps.CameraFieldOfView then
		hostCamera.CFrame = CFrame.new(unpack(firstProps.CameraCFrame))
		hostCamera.FieldOfView = firstProps.CameraFieldOfView
	else
		hostCamera.FieldOfView = DEFAULT_CAMERA_FOV
		local cameraPosition = hostPart.Position + Vector3.new(DEFAULT_CAMERA_DISTANCE * 0.75, DEFAULT_CAMERA_DISTANCE * 0.5, DEFAULT_CAMERA_DISTANCE * 0.75)
		hostCamera.CFrame = CFrame.lookAt(cameraPosition, hostPart.Position)
	end

	for _, props in ipairs(propertiesList) do
		local emitterData = {
			-- (All existing properties remain here)
			Texture = props.Texture or "",
			Rate = props.Rate or 10,
			Drag = props.Drag or 0,
			Lifetime = props.Lifetime and deserialize("NumberRange", props.Lifetime) or NumberRange.new(1),
			Speed = props.Speed and deserialize("NumberRange", props.Speed) or NumberRange.new(5),
			Rotation = props.Rotation and deserialize("NumberRange", props.Rotation) or NumberRange.new(0, 360),
			RotSpeed = props.RotSpeed and deserialize("NumberRange", props.RotSpeed) or NumberRange.new(0),
			Size = (props.Size and props.Size.Keypoints) and deserialize("NumberSequence", props.Size.Keypoints) or NumberSequence.new(1),
			Color = (props.Color and props.Color.Keypoints) and deserialize("ColorSequence", props.Color.Keypoints) or ColorSequence.new(Color3.new(1,1,1)),
			Transparency = (props.Transparency and props.Transparency.Keypoints) and deserialize("NumberSequence", props.Transparency.Keypoints) or NumberSequence.new(0),
			Acceleration = props.Acceleration and Vector3.new(unpack(props.Acceleration)) or Vector3.new(0,0,0),
			SpreadAngle = props.SpreadAngle and Vector2.new(unpack(props.SpreadAngle)) or Vector2.new(0,0),
			EmissionDirection = props.EmissionDirection and Enum.NormalId[props.EmissionDirection] or Enum.NormalId.Top,
			Orientation = props.Orientation and Enum.ParticleOrientation[props.Orientation] or Enum.ParticleOrientation.FacingCamera,
			EmitDuration = props.EmitDuration,
			EmitDelay = props.EmitDelay,
			EmitCount = props.EmitCount,

			-- ==================================================================
			-- FLIPBOOK PROPERTIES (NEW)
			-- ==================================================================
			FlipbookLayout = props.FlipbookLayout and Enum.ParticleFlipbookLayout[props.FlipbookLayout] or Enum.ParticleFlipbookLayout.None,
			FlipbookMode = props.FlipbookMode and Enum.ParticleFlipbookMode[props.FlipbookMode] or Enum.ParticleFlipbookMode.Loop,
			FlipbookFramerate = props.FlipbookFramerate or 15,
			FlipbookStartRandom = props.FlipbookStartRandom or false,
			-- Correctly deserialize the TextureSize table into a Vector2
			TextureSize = props.TextureSize and Vector2.new(unpack(props.TextureSize)) or nil,
		}

		local viewportEmitter = ViewportEmitter.new(emitterData, hostPart, viewportFrame, hostCamera)
		itemJanitor:Add(viewportEmitter)
		viewportEmitter:Start()
	end

	local nameLabel = instance:FindFirstChild("Frame", true):FindFirstChild("Name", true)
	if nameLabel and nameLabel:IsA("TextLabel") then nameLabel.Text = data.Name or "Unnamed VFX" end

	local gridIndex = dataIndex
	local row = math.floor((gridIndex - 1) / self.itemsPerRow)
	local col = (gridIndex - 1) % self.itemsPerRow
	local xPos = PADDING + col * (self.cellSize + PADDING)
	local yPos = PADDING + (row + 1) * (self.cellSize + PADDING)

	instance.Name = "VFXTemplate_" .. tostring(dataIndex)
	instance.Position = UDim2.fromOffset(xPos, yPos)
	instance.Visible = true
	instance.Parent = self.frame

	self.activeItems[dataIndex] = { instance = instance, janitor = itemJanitor }
end


-- (The rest of VFXViewportController.lua remains unchanged)
function VFXViewportController:_unloadItem(dataIndex)
	local itemData = self.activeItems[dataIndex]
	if itemData then
		itemData.janitor:Cleanup()
		itemData.instance.Parent = nil
		table.insert(self.inactivePool, itemData.instance)
		self.activeItems[dataIndex] = nil
	end
end

function VFXViewportController:_setupListeners()
	if not self.eventJanitor then return end
	self.eventJanitor:Add(self.frame:GetPropertyChangedSignal("CanvasPosition"):Connect(function()
		self:_requestUpdateVisibleItems()
	end))
	self.eventJanitor:Add(self.frame:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()
		self:recalculateLayout()
	end))
end

function VFXViewportController:recalculateLayout()
	if not self.isActive or not self.frame.Parent or not self.addButton.Parent then return end
	local frameWidth = self.frame.AbsoluteSize.X - self.frame.ScrollBarThickness
	self.cellSize = self.template.Size.X.Offset
	if self.cellSize <= 0 then self.cellSize = 128 end
	self.itemsPerRow = math.max(1, math.floor((frameWidth + PADDING) / (self.cellSize + PADDING)))
	self.totalRows = math.ceil((#self.dataSource + 1) / self.itemsPerRow)
	local canvasHeight = (self.totalRows * (self.cellSize + PADDING)) + PADDING
	self.frame.CanvasSize = UDim2.fromOffset(0, canvasHeight)
	self.addButton.Position = UDim2.fromOffset(PADDING, PADDING)
	for dataIndex, itemData in pairs(self.activeItems) do
		local gridIndex = dataIndex
		local row = math.floor((gridIndex - 1) / self.itemsPerRow)
		local col = (gridIndex - 1) % self.itemsPerRow
		local xPos = PADDING + col * (self.cellSize + PADDING)
		local yPos = PADDING + (row + 1) * (self.cellSize + PADDING)
		itemData.instance.Position = UDim2.fromOffset(xPos, yPos)
	end
	self:_requestUpdateVisibleItems()
end

function VFXViewportController:_requestUpdateVisibleItems()
	if not self.isActive or self.updateLayoutRequested then return end
	self.updateLayoutRequested = true
	task.defer(function()
		if self.isActive and self.frame.Parent then
			self:_updateVisibleItems()
		end
		self.updateLayoutRequested = false
	end)
end

function VFXViewportController:_updateVisibleItems()
	if not self.isActive or not self.frame.Parent or self.itemsPerRow == 0 then return end
	local effectiveRowHeight = self.cellSize + PADDING
	if effectiveRowHeight <= 0 then return end
	local viewportY, viewportHeight = self.frame.CanvasPosition.Y, self.frame.AbsoluteSize.Y
	if viewportY == nil or viewportHeight == nil or self.totalRows == nil then return end
	local firstVisibleRow = math.max(0, math.floor(viewportY / effectiveRowHeight) - BUFFER_ROWS)
	local lastVisibleRow = math.min(self.totalRows - 1, math.ceil((viewportY + viewportHeight) / effectiveRowHeight) - 1 + BUFFER_ROWS)
	if lastVisibleRow < firstVisibleRow then return end
	local visibleDataIndices = {}
	for row = firstVisibleRow, lastVisibleRow do
		for col = 0, self.itemsPerRow - 1 do
			local gridIndex = row * self.itemsPerRow + col
			local dataIndex = gridIndex
			if dataIndex > 0 and dataIndex <= #self.dataSource then
				visibleDataIndices[dataIndex] = true
			end
		end
	end
	local itemsToUnload = {}
	for loadedDataIndex in pairs(self.activeItems) do
		if not visibleDataIndices[loadedDataIndex] then
			table.insert(itemsToUnload, loadedDataIndex)
		end
	end
	for _, indexToUnload in ipairs(itemsToUnload) do
		self:_unloadItem(indexToUnload)
	end
	for dataIndexToLoad in pairs(visibleDataIndices) do
		if not self.activeItems[dataIndexToLoad] then
			self:_loadItem(dataIndexToLoad)
		end
	end
end

function VFXViewportController:_getTemplateInstance()
	if #self.inactivePool > 0 then return table.remove(self.inactivePool)
	else return self.template:Clone() end
end
function VFXViewportController:_clearAllItems()
	for index in pairs(self.activeItems) do self:_unloadItem(index) end
end
function VFXViewportController:Destroy()
	self:_clearAllItems()
	if self.addButton then self.addButton.Parent = nil end
	self.janitor:Cleanup()
	setmetatable(self, nil)
end

return VFXViewportController