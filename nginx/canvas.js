(function() {
    console.log("NIO 视频助手已加载");

    // 1. 创建画布
    var canvas = document.createElement("canvas");
    var ctx = canvas.getContext("2d", { alpha: false });
    // 默认隐藏，不占任何空间
    canvas.style.cssText = "display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:99999; background:#000;";
    document.body.appendChild(canvas);

    // 2. 创建切换按钮
    var btn = document.createElement("button");
    btn.style.cssText = "position:fixed; top:80px; left:20px; z-index:100000; padding:10px 20px; font-weight:bold; color:white; border:none; border-radius:30px; font-size:14px; cursor:pointer; box-shadow:0 4px 10px rgba(0,0,0,0.6); transition: all 0.3s;";
    document.body.appendChild(btn);

    var isDrivingMode = false; // 默认：选片模式
    var videoElement = null;
    var renderLoop = null;

    // 更新界面状态
    function updateUI() {
        if (isDrivingMode) {
            // === 行驶模式 ===
            canvas.style.display = "block"; // 显示画布
            btn.innerText = "🚗 行驶中 (点击解锁)";
            btn.style.background = "rgba(220, 38, 38, 0.9)"; // 红
            
            // 隐藏真视频
            if (videoElement) {
                videoElement.style.opacity = "0.01";
                // 必须 fixed 才能保证画面不乱跑，但层级要低
                videoElement.style.position = "fixed";
                videoElement.style.zIndex = "-1";
                videoElement.style.top = "0";
                videoElement.style.left = "0";
            }
        } else {
            // === 选片模式 ===
            canvas.style.display = "none"; // 隐藏画布
            btn.innerText = "🔓 选片模式 (点击锁定)";
            btn.style.background = "rgba(22, 163, 74, 0.9)"; // 绿
            
            // 恢复真视频显示，清除 fixed 定位
            if (videoElement) {
                videoElement.style.opacity = "1";
                videoElement.style.position = "static"; // 关键：恢复正常文档流
                videoElement.style.zIndex = "auto";
            }
        }
    }

    // 初始化
    updateUI();

    btn.onclick = function() {
        isDrivingMode = !isDrivingMode;
        updateUI();
    };

    // 监控视频标签
    setInterval(function() {
        var v = document.querySelector("video");
        if (v && v !== videoElement) {
            videoElement = v;
            updateUI(); // 应用当前状态
            
            // 点击画布控制暂停
            canvas.onclick = function() {
                if (videoElement.paused) videoElement.play(); 
                else videoElement.pause();
            };

            if (renderLoop) cancelAnimationFrame(renderLoop);
            loop();
        }
        // 强制维持状态
        if (videoElement && isDrivingMode) {
             if (videoElement.style.opacity !== "0.01") updateUI();
        }
    }, 1000);

    // 渲染循环
    function loop() {
        if (isDrivingMode && videoElement && !videoElement.paused && !videoElement.ended) {
            if (canvas.width !== window.innerWidth) canvas.width = window.innerWidth;
            if (canvas.height !== window.innerHeight) canvas.height = window.innerHeight;
            
            var vw = videoElement.videoWidth; var vh = videoElement.videoHeight;
            var cw = canvas.width; var ch = canvas.height;
            var scale = Math.min(cw / vw, ch / vh);
            var w = vw * scale; var h = vh * scale;
            var x = (cw - w) / 2; var y = (ch - h) / 2;

            ctx.fillStyle = "#000";
            ctx.fillRect(0, 0, cw, ch);
            ctx.drawImage(videoElement, x, y, w, h);
        }
        renderLoop = requestAnimationFrame(loop);
    }
    
    // 防止后台黑屏
    Object.defineProperty(document, "hidden", {get: function() {return false;}});
})();