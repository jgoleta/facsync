(function () {
  const bell = document.getElementById("notificationBell");
  if (!bell) return;
  const studentFeedback = window.studentFeedback;

  const endpoint = "/api/notifications/";
  const count = document.getElementById("notificationCount");
  const wrapper = bell.closest(".notification-nav");
  let menu;

  function csrfToken() {
    const token = document.querySelector("[name=csrfmiddlewaretoken]");
    if (token) return token.value;
    const cookie = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
  }

  function updateCount(value) {
    const unread = Number(value) || 0;
    count.textContent = unread > 99 ? "99+" : String(unread);
    count.classList.toggle("hidden", unread === 0);
  }

  function createMenu() {
    if (menu) return menu;
    menu = document.createElement("section");
    menu.className = "notification-menu hidden";
    menu.setAttribute("aria-label", "Notifications");
    menu.innerHTML = `
      <div class="notification-menu-header">
        <h2>Notifications</h2>
        <button type="button" class="notification-mark-all">Mark all read</button>
      </div>
      <div class="notification-list"></div>
    `;
    wrapper.appendChild(menu);
    menu.querySelector(".notification-mark-all").addEventListener("click", async () => {
      studentFeedback?.showLoading("Marking notifications as read...");
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "X-CSRFToken": csrfToken(), "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        if (!response.ok) throw new Error("Unable to mark notifications as read.");
        studentFeedback?.showToast("Notifications marked as read.");
      } catch (error) {
        studentFeedback?.showToast(error.message, true);
      } finally {
        studentFeedback?.hideLoading();
      }
      await loadNotifications();
    });
    return menu;
  }

  function render(notifications) {
    const list = createMenu().querySelector(".notification-list");
    list.replaceChildren();
    if (!notifications.length) {
      const empty = document.createElement("p");
      empty.className = "notification-empty";
      empty.textContent = "You have no notifications.";
      list.appendChild(empty);
      return;
    }

    notifications.forEach((notification) => {
      const item = document.createElement("article");
      item.className = `notification-item${notification.is_read ? "" : " unread"}`;

      const content = document.createElement("div");
      content.className = "notification-item-content";
      content.tabIndex = 0;
      const title = document.createElement("strong");
      title.className = "notification-item-title";
      title.textContent = notification.title;
      const message = document.createElement("span");
      message.className = "notification-item-message";
      message.textContent = notification.message;
      const time = document.createElement("time");
      time.className = "notification-item-time";
      time.dateTime = notification.created_at;
      time.textContent = new Date(notification.created_at).toLocaleString();
      content.append(title, message, time);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "notification-remove";
      remove.setAttribute("aria-label", "Remove notification");
      remove.textContent = "×";
      remove.addEventListener("click", async (event) => {
        event.stopPropagation();
        studentFeedback?.showLoading("Removing notification...");
        try {
          const response = await fetch(endpoint, {
            method: "DELETE",
            headers: { "X-CSRFToken": csrfToken(), "Content-Type": "application/json" },
            body: JSON.stringify({ notification_id: notification.id }),
          });
          if (!response.ok) throw new Error("Unable to remove notification.");
          studentFeedback?.showToast("Notification removed successfully.");
        } catch (error) {
          studentFeedback?.showToast(error.message, true);
        } finally {
          studentFeedback?.hideLoading();
        }
        await loadNotifications();
      });

      async function openNotification() {
        if (!notification.is_read) {
          studentFeedback?.showLoading("Opening notification...");
          try {
            const response = await fetch(endpoint, {
              method: "POST",
              headers: { "X-CSRFToken": csrfToken(), "Content-Type": "application/json" },
              body: JSON.stringify({ notification_id: notification.id }),
            });
            if (!response.ok) throw new Error("Unable to update notification.");
          } catch (error) {
            studentFeedback?.showToast(error.message, true);
            return;
          } finally {
            studentFeedback?.hideLoading();
          }
        }
        if (notification.url) window.location.href = notification.url;
        else await loadNotifications();
      }
      content.addEventListener("click", openNotification);
      content.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") openNotification();
      });
      item.append(content, remove);
      list.appendChild(item);
    });
  }

  async function loadNotifications() {
    try {
      const response = await fetch(endpoint);
      if (!response.ok) return;
      const data = await response.json();
      updateCount(data.unread_count);
      render(data.notifications || []);
    } catch (error) {
      // Keep the navigation usable if notifications are temporarily unavailable.
    }
  }

  bell.addEventListener("click", async () => {
    const nextOpen = menu ? menu.classList.contains("hidden") : true;
    createMenu().classList.toggle("hidden", !nextOpen);
    bell.setAttribute("aria-expanded", String(nextOpen));
    if (nextOpen) await loadNotifications();
  });

  document.addEventListener("click", (event) => {
    if (menu && !wrapper.contains(event.target)) {
      menu.classList.add("hidden");
      bell.setAttribute("aria-expanded", "false");
    }
  });

  loadNotifications();
  window.setInterval(loadNotifications, 30000);
})();
